import pytest
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxPresenceFactory,
    NestingBoxImageFactory,
    NestingBoxPresencePeriodFactory,
    NestingBoxFactory,
)


@pytest.mark.django_db
class TestTimelineViews:
    def test_timeline_view(self, client):
        url = reverse("timeline")
        response = client.get(url)
        assert response.status_code == 200

    def test_timeline_view_emits_timeline_config_json_script(self, client):
        """The JS side reads group data via <script id='timeline-config'
        type='application/json'>. Regression test that the config blob
        is present and contains the chickens/URLs we expect."""
        ChickenFactory(name="Henrietta")
        response = client.get(reverse("timeline"))
        content = response.content.decode()
        assert 'id="timeline-config"' in content
        assert 'type="application/json"' in content
        # Chicken name is rendered inside the JSON, not inline in JS
        assert "Henrietta" in content
        # URLs are baked in for the JS to read
        assert reverse("timeline_data") in content
        assert reverse("timeline_images") in content

    def test_timeline_view_escapes_dangerous_chicken_names(self, client):
        """Regression test for a reflected-XSS vector on the timeline
        page. Previously the template interpolated chicken names into
        a JavaScript object literal:

            {% for chicken in chickens %}
            { id: '…', content: '{{ chicken.name }}', stack: false },
            {% endfor %}

        A chicken named ``"; alert(1); //`` would break out of the
        string literal and execute arbitrary JS. A name containing
        ``</script>`` would end the inline <script> tag prematurely
        and inject a new one with whatever followed.

        The fix: json_script emits the data inside a
        ``<script type="application/json">`` block, which the browser
        parses as text data only — and json_script itself escapes
        ``<``, ``>``, ``&``, and line separators as their ``\\uNNNN``
        equivalents so the closing-tag attack is impossible.
        """
        ChickenFactory(name="attack</script><script>alert(1)</script>")

        response = client.get(reverse("timeline"))
        content = response.content.decode()
        assert response.status_code == 200

        # The injected </script> must not appear literally in the
        # response — if it did, the browser would close the JSON script
        # block and start executing whatever came next.
        assert "<script>alert(1)</script>" not in content
        # The legitimate <script> tags on the page (htmx, bootstrap,
        # timeline_utils, timeline_page) should exist but none of them
        # should be inside the timeline-config element.
        config_start = content.find('id="timeline-config"')
        assert config_start != -1
        # Find the matching </script> after the config element's opening
        config_close = content.find("</script>", config_start)
        assert config_close != -1
        config_block = content[config_start:config_close]
        # Inside the config element, there must be no </script>
        assert "</script>" not in config_block.lower()
        assert "<script>" not in config_block.lower()
        # The escaped form is what we expect — json_script replaces
        # "<" with "\u003C".
        assert "\\u003C" in config_block or "\\u003c" in config_block

    def test_timeline_data(self, client):
        url = reverse("timeline_data")

        # Create some data
        now = timezone.now()
        egg = EggFactory(laid_at=now)
        presence = NestingBoxPresenceFactory(present_at=now)

        # Test without params
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == []

        # Test with range covering now but zoomed out (2 hours)
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()
        response = client.get(f"{url}?start={start}&end={end}")
        assert response.status_code == 200
        data = response.json()
        # Should only have egg, not presence
        assert len(data) == 1
        ids = [item["id"] for item in data]
        assert f"egg_{egg.id}" in ids
        assert f"presence_{presence.id}" not in ids

        # Test with range covering now and zoomed in (2 minutes)
        start = (now - timedelta(minutes=1)).isoformat()
        end = (now + timedelta(minutes=1)).isoformat()
        response = client.get(f"{url}?start={start}&end={end}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        ids = [item["id"] for item in data]
        assert f"egg_{egg.id}" in ids
        assert f"presence_{presence.id}" in ids

        # Test with range NOT covering now
        start = (now - timedelta(hours=5)).isoformat()
        end = (now - timedelta(hours=4)).isoformat()
        response = client.get(f"{url}?start={start}&end={end}")
        assert response.json() == []

    def test_timeline_data_invalid_dates(self, client):
        url = reverse("timeline_data")
        response = client.get(f"{url}?start=not-a-date&end=2026-02-14")
        assert response.status_code == 200
        assert response.json() == []

    def test_timeline_images_edge_cases(self, client):
        now = timezone.now()
        NestingBoxImageFactory(created_at=now)
        url = reverse("timeline_images")
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        # n=1
        response = client.get(f"{url}?start={start}&end={end}&n=1")
        assert len(response.json()) == 1

        # invalid n
        response = client.get(f"{url}?start={start}&end={end}&n=abc")
        assert response.status_code == 200
        assert (
            len(response.json()) == 1
        )  # Should default to 100, but we only have 1 image

        # n=0 should be treated as n=1
        response = client.get(f"{url}?start={start}&end={end}&n=0")
        assert len(response.json()) == 1

    def test_partial_image_at_time_scenarios(self, client):
        t1 = timezone.now() - timedelta(minutes=20)
        t2 = timezone.now() - timedelta(minutes=10)
        img1 = NestingBoxImageFactory(created_at=t1)
        img2 = NestingBoxImageFactory(created_at=t2)

        url = reverse("partial_image_at_time")

        # 1. Target exactly at t1
        response = client.get(f"{url}?t={t1.isoformat()}")
        assert response.context["latest_image"] == img1

        # 2. Target between t1 and t2 (should pick img1 as it's the latest BEFORE or AT)
        t_mid = t1 + timedelta(minutes=5)
        response = client.get(f"{url}?t={t_mid.isoformat()}")
        assert response.context["latest_image"] == img1

        # 3. Target before t1 (should pick img1 because it's the closest after if none before)
        t_before = t1 - timedelta(minutes=5)
        response = client.get(f"{url}?t={t_before.isoformat()}")
        assert response.context["latest_image"] == img1

        # 4. Target after t2
        t_after = t2 + timedelta(minutes=5)
        response = client.get(f"{url}?t={t_after.isoformat()}")
        assert response.context["latest_image"] == img2

    def test_timeline_data_box_colors(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        box_left = NestingBoxFactory(name="left")
        box_right = NestingBoxFactory(name="right")

        period = NestingBoxPresencePeriodFactory(
            nesting_box=box_left, started_at=now, ended_at=now + timedelta(minutes=1)
        )
        presence = NestingBoxPresenceFactory(nesting_box=box_right, present_at=now)

        start = (now - timedelta(minutes=1)).isoformat()
        end = (now + timedelta(minutes=1)).isoformat()

        response = client.get(f"{url}?start={start}&end={end}")
        data = response.json()

        period_item = next(item for item in data if item["id"] == f"period_{period.id}")
        presence_item = next(
            item for item in data if item["id"] == f"presence_{presence.id}"
        )

        assert "box-left" in period_item["className"]
        assert "timeline-period" in period_item["className"]
        assert "box-right" in presence_item["className"]
        assert "timeline-presence-dot" in presence_item["className"]

    # ── egg quality rendering ─────────────────────────────────────────────────

    def test_saleable_egg_has_saleable_class(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        egg = EggFactory(laid_at=now, quality="saleable")
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        item = next(i for i in data if i["id"] == f"egg_{egg.id}")
        assert "timeline-egg" in item["className"]
        assert "timeline-egg--saleable" in item["className"]

    def test_edible_egg_has_edible_class(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        egg = EggFactory(laid_at=now, quality="edible")
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        item = next(i for i in data if i["id"] == f"egg_{egg.id}")
        assert "timeline-egg" in item["className"]
        assert "timeline-egg--edible" in item["className"]

    def test_messy_egg_has_messy_class(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        egg = EggFactory(laid_at=now, quality="messy")
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        item = next(i for i in data if i["id"] == f"egg_{egg.id}")
        assert "timeline-egg" in item["className"]
        assert "timeline-egg--messy" in item["className"]

    def test_eggs_of_all_quality_tiers_appear_in_timeline(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        messy = EggFactory(laid_at=now, quality="messy")
        edible = EggFactory(laid_at=now, quality="edible")
        saleable = EggFactory(laid_at=now, quality="saleable")
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        ids = {i["id"] for i in data}
        assert f"egg_{messy.id}" in ids
        assert f"egg_{edible.id}" in ids
        assert f"egg_{saleable.id}" in ids

    # ── presence periods in timeline data ─────────────────────────────────────

    def test_period_appears_in_timeline_data(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            started_at=now, ended_at=now + timedelta(minutes=2)
        )
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        ids = {i["id"] for i in data}
        assert f"period_{period.id}" in ids

    def test_period_outside_range_excluded(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        NestingBoxPresencePeriodFactory(
            started_at=now - timedelta(hours=5),
            ended_at=now - timedelta(hours=4),
        )
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        assert all(not i["id"].startswith("period_") for i in data)

    def test_period_item_has_range_type(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            started_at=now, ended_at=now + timedelta(minutes=2)
        )
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        item = next(i for i in data if i["id"] == f"period_{period.id}")
        assert item["type"] == "range"

    def test_period_item_group_set_to_chicken(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        chicken = ChickenFactory()
        period = NestingBoxPresencePeriodFactory(
            chicken=chicken, started_at=now, ended_at=now + timedelta(minutes=2)
        )
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        item = next(i for i in data if i["id"] == f"period_{period.id}")
        assert item["group"] == f"chicken_{chicken.pk}"

    # ── egg group assignment ──────────────────────────────────────────────────

    def test_egg_group_set_to_chicken(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        chicken = ChickenFactory()
        egg = EggFactory(chicken=chicken, laid_at=now)
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        item = next(i for i in data if i["id"] == f"egg_{egg.id}")
        assert item["group"] == f"chicken_{chicken.pk}"

    def test_egg_without_chicken_group_is_unknown(self, client):
        url = reverse("timeline_data")
        now = timezone.now()
        egg = EggFactory(chicken=None, laid_at=now)
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        data = client.get(f"{url}?start={start}&end={end}").json()
        item = next(i for i in data if i["id"] == f"egg_{egg.id}")
        assert item["group"] == "unknown"

    # ── timeline_images sampling ──────────────────────────────────────────────

    def test_timeline_images_sampling_covers_end(self, client):
        """When more images exist than n, the last image in range is always included."""
        url = reverse("timeline_images")
        now = timezone.now()
        images = [
            NestingBoxImageFactory(created_at=now + timedelta(minutes=i))
            for i in range(10)
        ]
        start = (now - timedelta(minutes=1)).isoformat()
        end = (now + timedelta(minutes=11)).isoformat()

        response = client.get(f"{url}?start={start}&end={end}&n=3")
        data = response.json()
        returned_timestamps = {d["timestamp"] for d in data}
        assert images[-1].created_at.isoformat() in returned_timestamps

    def test_timeline_images_no_images_returns_empty(self, client):
        url = reverse("timeline_images")
        now = timezone.now()
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()
        assert client.get(f"{url}?start={start}&end={end}").json() == []

    def test_timeline_images_missing_params_returns_empty(self, client):
        assert client.get(reverse("timeline_images")).json() == []
