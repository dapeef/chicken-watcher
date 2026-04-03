import pytest
import json
from datetime import timedelta, datetime, timezone as dt_timezone
from django.urls import reverse
from django.utils import timezone
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
    NestingBoxPresencePeriodFactory,
)
from web_app.views.chickens import nesting_time_of_day, BUCKET_MINUTES, BUCKETS_PER_DAY


def make_period(started_at, ended_at):
    """Build an unsaved NestingBoxPresencePeriod-like object for unit tests."""
    p = NestingBoxPresencePeriodFactory.build(
        started_at=started_at,
        ended_at=ended_at,
    )
    return p


def utc(hour, minute=0, day=1):
    """Return a UTC-aware datetime on an arbitrary fixed date."""
    return datetime(2024, 1, day, hour, minute, tzinfo=dt_timezone.utc)


class TestNestingTimeOfDay:
    def test_empty_periods(self):
        counts = nesting_time_of_day([])
        assert len(counts) == BUCKETS_PER_DAY
        assert all(c == 0 for c in counts)

    def test_single_period_within_one_bucket(self):
        # 10:02 – 10:07 falls entirely inside bucket 10:00–10:10 (index 60)
        period = make_period(utc(10, 2), utc(10, 7))
        counts = nesting_time_of_day([period])
        bucket = (10 * 60) // BUCKET_MINUTES  # index 60
        assert counts[bucket] == 1
        assert sum(counts) == 1

    def test_period_spanning_two_buckets(self):
        # 10:05 – 10:15 spans buckets 10:00 (index 60) and 10:10 (index 61)
        period = make_period(utc(10, 5), utc(10, 15))
        counts = nesting_time_of_day([period])
        assert counts[60] == 1
        assert counts[61] == 1
        assert sum(counts) == 2

    def test_same_chicken_same_bucket_two_different_days(self):
        # Two periods on different days, both in the 10:00 bucket → count = 2
        p1 = make_period(utc(10, 2, day=1), utc(10, 7, day=1))
        p2 = make_period(utc(10, 2, day=2), utc(10, 7, day=2))
        counts = nesting_time_of_day([p1, p2])
        bucket = (10 * 60) // BUCKET_MINUTES
        assert counts[bucket] == 2

    def test_same_day_two_periods_same_bucket_counted_once(self):
        # Two periods on the same day, both in the 10:00 bucket → count = 1
        p1 = make_period(utc(10, 0, day=1), utc(10, 5, day=1))
        p2 = make_period(utc(10, 5, day=1), utc(10, 9, day=1))
        counts = nesting_time_of_day([p1, p2])
        bucket = (10 * 60) // BUCKET_MINUTES
        assert counts[bucket] == 1

    def test_period_spanning_midnight(self):
        # 23:55 day 1 to 00:05 day 2 — spans bucket 23:50 (index 143) and 00:00 (index 0)
        p = make_period(utc(23, 55, day=1), utc(0, 5, day=2))
        counts = nesting_time_of_day([p])
        assert counts[0] == 1  # 00:00 bucket, hit on day 2
        assert counts[143] == 1  # 23:50 bucket, hit on day 1


@pytest.mark.django_db
class TestChickenViews:
    def test_chicken_list_view(self, client):
        ChickenFactory(name="Bertha")
        ChickenFactory(name="Alice")
        url = reverse("chicken_list")

        # Test default sorting (name)
        response = client.get(url)
        assert response.status_code == 200
        chickens = response.context["object_list"]
        assert len(chickens) == 2
        assert chickens[0].name == "Alice"
        assert chickens[1].name == "Bertha"

        # Test explicit sorting
        response = client.get(url + "?sort=-name")
        chickens = response.context["object_list"]
        assert chickens[0].name == "Bertha"
        assert chickens[1].name == "Alice"

    def test_chicken_detail_view(self, client):
        chicken = ChickenFactory()
        EggFactory.create_batch(
            5, chicken=chicken, laid_at=timezone.now() - timedelta(days=1)
        )

        url = reverse("chicken_detail", kwargs={"pk": chicken.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["hen"] == chicken
        assert response.context["stats"]["total"] == 5

        # Check chart data
        assert "chart_labels" in response.context
        assert "chart_daily" in response.context
        daily = json.loads(response.context["chart_daily"])
        assert sum(daily) == 5

    def test_chicken_timeline_data_returns_periods_and_eggs(self, client):
        chicken = ChickenFactory()
        box = NestingBoxFactory(name="left")
        now = timezone.now()

        period = NestingBoxPresencePeriodFactory(
            chicken=chicken,
            nesting_box=box,
            started_at=now - timedelta(minutes=30),
            ended_at=now - timedelta(minutes=10),
        )
        egg = EggFactory(
            chicken=chicken,
            nesting_box=box,
            laid_at=now - timedelta(minutes=15),
        )

        start = (now - timedelta(hours=1)).isoformat()
        end = now.isoformat()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url, {"start": start, "end": end})

        assert response.status_code == 200
        data = json.loads(response.content)
        ids = {item["id"] for item in data}
        assert f"period_{period.id}" in ids
        assert f"egg_{egg.id}" in ids

    def test_chicken_timeline_data_excludes_other_chickens(self, client):
        chicken = ChickenFactory()
        other = ChickenFactory()
        box = NestingBoxFactory(name="left")
        now = timezone.now()

        NestingBoxPresencePeriodFactory(
            chicken=other,
            nesting_box=box,
            started_at=now - timedelta(minutes=30),
            ended_at=now - timedelta(minutes=10),
        )

        start = (now - timedelta(hours=1)).isoformat()
        end = now.isoformat()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url, {"start": start, "end": end})

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data == []

    def test_chicken_timeline_data_missing_params_returns_empty(self, client):
        chicken = ChickenFactory()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert json.loads(response.content) == []

    def test_chicken_timeline_data_invalid_chicken_returns_404(self, client):
        url = reverse("chicken_timeline_data", kwargs={"pk": 99999})
        response = client.get(url)
        assert response.status_code == 404
