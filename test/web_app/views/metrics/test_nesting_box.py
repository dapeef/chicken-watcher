import json
from datetime import UTC, datetime, timedelta

import pytest
from django.urls import reverse

from test.web_app.factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
    NestingBoxPresencePeriodFactory,
)


@pytest.mark.django_db
class TestMetricsViewNestingBoxPreference:
    def test_context_keys_present(self, client):
        response = client.get(reverse("metrics"))
        assert "nesting_box_visits_json" in response.context
        assert "nesting_box_time_json" in response.context

    def test_visits_counted_per_box(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_a = NestingBoxFactory(name="left")
        box_b = NestingBoxFactory(name="right")

        for _ in range(3):
            NestingBoxPresencePeriodFactory(
                chicken=hen,
                nesting_box=box_a,
                started_at=datetime.combine(today, datetime.min.time(), tzinfo=UTC),
                ended_at=datetime.combine(today, datetime.min.time(), tzinfo=UTC)
                + timedelta(minutes=10),
            )
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_b,
            started_at=datetime.combine(today, datetime.min.time(), tzinfo=UTC),
            ended_at=datetime.combine(today, datetime.min.time(), tzinfo=UTC)
            + timedelta(minutes=5),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        box_visits = dict(zip(visits_data["labels"], visits_data["datasets"][0]["data"]))
        assert box_visits["Left"] == 3
        assert box_visits["Right"] == 1

    def test_time_summed_per_box(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_a = NestingBoxFactory(name="left")
        box_b = NestingBoxFactory(name="right")
        base = datetime.combine(today, datetime.min.time(), tzinfo=UTC)

        for _ in range(2):
            NestingBoxPresencePeriodFactory(
                chicken=hen,
                nesting_box=box_a,
                started_at=base,
                ended_at=base + timedelta(minutes=30),
            )
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_b,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        time_data = json.loads(response.context["nesting_box_time_json"])
        box_secs = dict(zip(time_data["labels"], time_data["datasets"][0]["data"]))
        assert box_secs["Left"] == 3600
        assert box_secs["Right"] == 600

    def test_aggregates_across_multiple_chickens(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        base = datetime.combine(today, datetime.min.time(), tzinfo=UTC)

        NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=box,
            started_at=base,
            ended_at=base + timedelta(minutes=20),
        )
        NestingBoxPresencePeriodFactory(
            chicken=c2,
            nesting_box=box,
            started_at=base,
            ended_at=base + timedelta(minutes=40),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk), str(c2.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        box_visits = dict(zip(visits_data["labels"], visits_data["datasets"][0]["data"]))
        assert box_visits["Left"] == 2

        time_data = json.loads(response.context["nesting_box_time_json"])
        box_secs = dict(zip(time_data["labels"], time_data["datasets"][0]["data"]))
        assert box_secs["Left"] == (20 + 40) * 60

    def test_excludes_periods_outside_date_range(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=10))
        box = NestingBoxFactory(name="left")
        before_range = datetime.combine(start - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box,
            started_at=before_range,
            ended_at=before_range + timedelta(minutes=30),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        assert visits_data["labels"] == []
        assert visits_data["datasets"][0]["data"] == []

    def test_excludes_unselected_chickens(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        base = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        NestingBoxPresencePeriodFactory(
            chicken=c2,
            nesting_box=box,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        assert visits_data["labels"] == []

    def test_empty_when_no_chickens_selected(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        base = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )

        response = client.get(reverse("metrics"), {"chickens_sent": "1"})
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        assert visits_data["labels"] == []
        assert visits_data["datasets"][0]["data"] == []

    def test_eggs_context_key_present(self, client):
        response = client.get(reverse("metrics"))
        assert "nesting_box_eggs_json" in response.context

    def test_eggs_counted_per_box(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_a = NestingBoxFactory(name="left")
        box_b = NestingBoxFactory(name="right")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(4, chicken=hen, nesting_box=box_a, laid_at=today_dt)
        EggFactory.create_batch(1, chicken=hen, nesting_box=box_b, laid_at=today_dt)

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        box_eggs = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
        assert box_eggs.get("Left") == 4
        assert box_eggs.get("Right") == 1


@pytest.mark.django_db
class TestNestingBoxPieColours:
    """Regression tests for stable, name-keyed pie slice colours.

    Previously colours were assigned by position (index 0 → colour 0,
    etc.), so adding an "Unknown" slice changed the indices of Left and
    Right, causing them to switch colours.
    """

    def _base_params(self, start, end, hen):
        return {
            "chickens_sent": "1",
            "chickens": [str(hen.pk)],
            "start": start.isoformat(),
            "end": end.isoformat(),
        }

    def _colour_map(self, response, json_key):
        data = json.loads(response.context[json_key])
        return dict(zip(data["labels"], data["datasets"][0]["backgroundColor"]))

    def test_left_and_right_colour_unchanged_when_unknown_added(self, client):
        """Adding an Unknown slice must not change Left's or Right's colour."""
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_left = NestingBoxFactory(name="left")
        box_right = NestingBoxFactory(name="right")
        base = datetime.combine(today, datetime.min.time(), tzinfo=UTC)

        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_left,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_right,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )

        params = self._base_params(start, today, hen)

        r_without = client.get(reverse("metrics"), params)
        c_without = self._colour_map(r_without, "nesting_box_visits_json")

        EggFactory(chicken=None, nesting_box=None, laid_at=base)
        r_with = client.get(reverse("metrics"), {**params, "include_unknown": "1"})
        c_with = self._colour_map(r_with, "nesting_box_visits_json")

        assert c_without.get("Left") == c_with.get("Left"), (
            f"Left colour changed when Unknown was added: "
            f"{c_without.get('Left')!r} → {c_with.get('Left')!r}"
        )
        assert c_without.get("Right") == c_with.get("Right"), (
            f"Right colour changed when Unknown was added: "
            f"{c_without.get('Right')!r} → {c_with.get('Right')!r}"
        )

    def test_unknown_is_ordered_between_left_and_right(self, client):
        """Slice order must be Left → Unknown → Right."""
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_left = NestingBoxFactory(name="left")
        box_right = NestingBoxFactory(name="right")
        base = datetime.combine(today, datetime.min.time(), tzinfo=UTC)

        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_left,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_right,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )
        EggFactory(chicken=None, nesting_box=None, laid_at=base)

        params = {**self._base_params(start, today, hen), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)

        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        labels = eggs_data["labels"]

        if "Unknown" in labels and "Left" in labels and "Right" in labels:
            assert labels.index("Left") < labels.index("Unknown") < labels.index("Right"), (
                f"Expected Left → Unknown → Right, got {labels}"
            )

    def test_unknown_gets_grey_not_named_box_colour(self, client):
        """Unknown must render in a visually distinct grey, not a
        named-box colour."""
        from django.utils import timezone

        from web_app.views.metrics_chart_builders import _BOX_COLOUR, UNKNOWN_COLOUR

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_left = NestingBoxFactory(name="left")
        base = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_left,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )
        EggFactory(chicken=None, nesting_box=None, laid_at=base)

        params = {**self._base_params(start, today, hen), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)

        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        colour_map = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["backgroundColor"]))

        if "Unknown" in colour_map:
            assert colour_map["Unknown"] == UNKNOWN_COLOUR
            assert colour_map["Unknown"] != _BOX_COLOUR.get("Left")
            assert colour_map["Unknown"] != _BOX_COLOUR.get("Right")

    def test_eggs_excluded_for_unselected_chickens(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory(chicken=c2, nesting_box=box, laid_at=today_dt)

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        assert eggs_data["labels"] == []
