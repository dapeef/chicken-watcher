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
                started_at=datetime.combine(
                    today, datetime.min.time(), tzinfo=UTC
                ),
                ended_at=datetime.combine(
                    today, datetime.min.time(), tzinfo=UTC
                )
                + timedelta(minutes=10),
            )
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_b,
            started_at=datetime.combine(
                today, datetime.min.time(), tzinfo=UTC
            ),
            ended_at=datetime.combine(
                today, datetime.min.time(), tzinfo=UTC
            )
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
        box_visits = dict(
            zip(visits_data["labels"], visits_data["datasets"][0]["data"])
        )
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
        box_visits = dict(
            zip(visits_data["labels"], visits_data["datasets"][0]["data"])
        )
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
        before_range = datetime.combine(
            start - timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
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
        assert box_eggs["Left"] == 4
        assert box_eggs["Right"] == 1

    def test_eggs_aggregated_across_chickens(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=c1, nesting_box=box, laid_at=today_dt)
        EggFactory.create_batch(3, chicken=c2, nesting_box=box, laid_at=today_dt)

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk), str(c2.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        box_eggs = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
        assert box_eggs["Left"] == 5

    def test_eggs_excluded_outside_date_range(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=10))
        box = NestingBoxFactory(name="left")
        before_range = datetime.combine(
            start - timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
        EggFactory(chicken=hen, nesting_box=box, laid_at=before_range)

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
        assert eggs_data["labels"] == []

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
