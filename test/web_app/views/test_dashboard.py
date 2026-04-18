from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from ..factories import (
    ChickenFactory,
    EggFactory,
    HardwareSensorFactory,
    NestingBoxFactory,
    NestingBoxPresencePeriodFactory,
)


@pytest.mark.django_db
class TestDashboardViews:
    def test_dashboard_view_returns_200(self, client):
        url = reverse("dashboard")
        response = client.get(url)
        assert response.status_code == 200

    def test_latest_presence_uses_presence_periods(self, client):
        """latest_presence context should contain NestingBoxPresencePeriod objects."""
        c1 = ChickenFactory(name="C1")
        b1 = NestingBoxFactory(name="Box1")
        period = NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=b1,
            started_at=timezone.now() - timedelta(minutes=10),
            ended_at=timezone.now() - timedelta(minutes=5),
        )

        response = client.get(reverse("dashboard"))
        assert response.status_code == 200

        latest_presence = list(response.context["latest_presence"])
        assert period in latest_presence

    def test_latest_presence_one_entry_per_box(self, client):
        """Only the most recent period per box is returned."""
        c1 = ChickenFactory(name="C1")
        b1 = NestingBoxFactory(name="Box1")

        NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=b1,
            started_at=timezone.now() - timedelta(minutes=20),
            ended_at=timezone.now() - timedelta(minutes=15),
        )
        latest = NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=b1,
            started_at=timezone.now() - timedelta(minutes=10),
            ended_at=timezone.now() - timedelta(minutes=5),
        )

        response = client.get(reverse("dashboard"))
        latest_presence = list(response.context["latest_presence"])

        box1_entries = [p for p in latest_presence if p.nesting_box == b1]
        assert len(box1_entries) == 1
        assert box1_entries[0] == latest

    def test_latest_presence_separate_entries_per_box(self, client):
        """One entry is returned for each box that has a period today."""
        c1 = ChickenFactory(name="C1")
        b1 = NestingBoxFactory(name="Box1")
        b2 = NestingBoxFactory(name="Box2")

        p1 = NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=b1,
            started_at=timezone.now() - timedelta(minutes=20),
            ended_at=timezone.now() - timedelta(minutes=15),
        )
        p2 = NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=b2,
            started_at=timezone.now() - timedelta(minutes=10),
            ended_at=timezone.now() - timedelta(minutes=5),
        )

        response = client.get(reverse("dashboard"))
        latest_presence = list(response.context["latest_presence"])

        assert p1 in latest_presence
        assert p2 in latest_presence

    def test_latest_presence_excludes_yesterday(self, client):
        """Periods that ended before today are not included."""
        c1 = ChickenFactory(name="C1")
        b1 = NestingBoxFactory(name="Box1")

        NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=b1,
            started_at=timezone.now() - timedelta(days=1, minutes=10),
            ended_at=timezone.now() - timedelta(days=1),
        )

        response = client.get(reverse("dashboard"))
        latest_presence = list(response.context["latest_presence"])
        assert latest_presence == []

    def test_presence_period_duration_property(self):
        """NestingBoxPresencePeriod.duration returns the correct timedelta."""
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory.build(
            started_at=now - timedelta(minutes=7),
            ended_at=now - timedelta(minutes=2),
        )
        assert period.duration == timedelta(minutes=5)

    def test_latest_presence_partial_renders_duration_and_departed(self, client):
        """The partial template renders duration and departed columns."""
        c1 = ChickenFactory(name="Henrietta")
        b1 = NestingBoxFactory(name="LeftBox")
        NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=b1,
            started_at=timezone.now() - timedelta(minutes=10),
            ended_at=timezone.now() - timedelta(minutes=5),
        )

        response = client.get(reverse("partial_latest_presence"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "Henrietta" in content
        assert "Leftbox" in content
        assert "Duration" in content
        assert "Departed" in content

    def test_partial_sensors(self, client):
        HardwareSensorFactory(name="rfid_test", is_connected=True)
        url = reverse("partial_sensors")
        response = client.get(url)
        assert response.status_code == 200
        assert b"rfid_test" in response.content
        assert b"Online" in response.content

    def test_other_partials(self, client):
        partials = [
            "partial_eggs_today",
            "partial_laid_chickens",
            "partial_latest_image",
            "partial_latest_presence",
            "partial_latest_events",
        ]
        for p in partials:
            url = reverse(p)
            response = client.get(url)
            assert response.status_code == 200


@pytest.mark.django_db
class TestLatestEventsPartial:
    url = reverse("partial_latest_events")

    def test_known_chicken_and_box_uses_names(self, client):
        hen = ChickenFactory(name="Hoppy")
        box = NestingBoxFactory(name="left")
        EggFactory(chicken=hen, nesting_box=box)

        response = client.get(self.url)
        content = response.content.decode()
        assert "Hoppy" in content
        assert "laid an egg in" in content
        assert "Left box" in content
        assert "laid an egg in" in content
        assert "Left box" in content

    def test_unknown_chicken_shows_unknown_hen(self, client):
        box = NestingBoxFactory(name="left")
        EggFactory(chicken=None, nesting_box=box)

        response = client.get(self.url)
        content = response.content.decode()
        assert "Unknown hen" in content
        assert "laid an egg in" in content
        assert "Left box" in content

    def test_unknown_nesting_box_shows_unknown_box(self, client):
        hen = ChickenFactory(name="Isla")
        EggFactory(chicken=hen, nesting_box=None)

        response = client.get(self.url)
        content = response.content.decode()
        assert "Isla" in content
        assert "unknown box" in content

    def test_both_unknown_shows_both_fallbacks(self, client):
        EggFactory(chicken=None, nesting_box=None)

        response = client.get(self.url)
        content = response.content.decode()
        assert "Unknown hen" in content
        assert "unknown box" in content

    def test_no_bare_chicken_name_without_context(self, client):
        """The old template rendered nothing for a null chicken; verify it no longer does."""
        EggFactory(chicken=None, nesting_box=None)

        response = client.get(self.url)
        content = response.content.decode()
        # Should not silently render an empty <strong></strong> for the chicken
        assert "<strong></strong>" not in content


@pytest.mark.django_db
class TestDashboardPartialQueryCount:
    """Each dashboard partial now only queries what its own panel
    needs, instead of the previous monolithic
    ``get_dashboard_context()`` that ran all 7 queries on every 5-second
    HTMX refresh (× 6 panels = 42 queries per cycle, idle)."""

    def _populate(self):
        """A realistic mix: a few chickens, eggs today, sensors, an
        image, and a presence period."""
        c1 = ChickenFactory(name="C1")
        c2 = ChickenFactory(name="C2")
        b1 = NestingBoxFactory(name="left")
        b2 = NestingBoxFactory(name="right")
        EggFactory(chicken=c1, nesting_box=b1)
        EggFactory(chicken=c2, nesting_box=b2)
        NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=b1,
            started_at=timezone.now() - timedelta(minutes=5),
            ended_at=timezone.now(),
        )
        HardwareSensorFactory(name="rfid_left_1", is_connected=True)
        HardwareSensorFactory(name="camera_cam", is_connected=False)

    def test_partial_eggs_today_is_cheap(self, client, django_assert_max_num_queries):
        self._populate()
        with django_assert_max_num_queries(3):
            response = client.get(reverse("partial_eggs_today"))
            assert response.status_code == 200

    def test_partial_laid_chickens_is_cheap(self, client, django_assert_max_num_queries):
        self._populate()
        with django_assert_max_num_queries(5):
            response = client.get(reverse("partial_laid_chickens"))
            assert response.status_code == 200

    def test_partial_sensors_is_cheap(self, client, django_assert_max_num_queries):
        self._populate()
        with django_assert_max_num_queries(3):
            response = client.get(reverse("partial_sensors"))
            assert response.status_code == 200

    def test_partial_latest_image_is_cheap(self, client, django_assert_max_num_queries):
        self._populate()
        with django_assert_max_num_queries(3):
            response = client.get(reverse("partial_latest_image"))
            assert response.status_code == 200

    def test_partial_latest_events_is_cheap(self, client, django_assert_max_num_queries):
        self._populate()
        with django_assert_max_num_queries(5):
            response = client.get(reverse("partial_latest_events"))
            assert response.status_code == 200

    def test_partial_latest_presence_is_cheap(self, client, django_assert_max_num_queries):
        self._populate()
        # latest_presence does one query per active box on SQLite;
        # with two boxes that's ~4 queries total. Postgres does 1.
        with django_assert_max_num_queries(8):
            response = client.get(reverse("partial_latest_presence"))
            assert response.status_code == 200
