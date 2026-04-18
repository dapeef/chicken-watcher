import pytest
from datetime import timedelta, datetime
from django.urls import reverse

from test.web_app.factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxPresencePeriodFactory,
)


@pytest.mark.django_db
class TestMetricsViewQueryCount:
    """The metrics view previously ran several per-hen queries inside
    loops (egg KDE, nesting TOD, age production), so query count grew
    linearly with the flock size. These tests pin the query count to
    a constant ceiling regardless of how many hens are chosen."""

    def _make_flock(self, n_hens: int, eggs_per_hen: int = 3):
        from django.utils import timezone

        today = timezone.localdate()
        for _ in range(n_hens):
            hen = ChickenFactory(date_of_birth=today - timedelta(days=365))
            for d in range(eggs_per_hen):
                EggFactory(
                    chicken=hen,
                    laid_at=timezone.make_aware(
                        datetime.combine(today - timedelta(days=d), datetime.min.time())
                    ),
                )
                NestingBoxPresencePeriodFactory(
                    chicken=hen,
                    started_at=timezone.make_aware(
                        datetime.combine(today - timedelta(days=d), datetime.min.time())
                    ),
                    ended_at=timezone.make_aware(
                        datetime.combine(today - timedelta(days=d), datetime.min.time())
                    )
                    + timedelta(minutes=5),
                )

    def test_query_count_is_bounded_at_10_hens(
        self, client, django_assert_max_num_queries
    ):
        self._make_flock(10)
        with django_assert_max_num_queries(40):
            response = client.get(reverse("metrics"))
            assert response.status_code == 200

    def test_query_count_does_not_grow_with_flock_size(
        self, client, django_assert_max_num_queries
    ):
        self._make_flock(20)
        with django_assert_max_num_queries(40):
            response = client.get(reverse("metrics"))
            assert response.status_code == 200
