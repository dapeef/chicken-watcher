"""
Tests for the custom QuerySet methods on each model.

These replace scattered filter-chains that previously lived in views and
management commands, so having a single test file for them makes it easy
to see the shape of the querying API we expose.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from web_app.models import Chicken, Egg, NestingBoxPresencePeriod

from .factories import (
    ChickenFactory,
    EggFactory,
    HardwareSensorFactory,
    NestingBoxFactory,
    NestingBoxImageFactory,
    NestingBoxPresencePeriodFactory,
)

# ---------------------------------------------------------------------------
# Chicken
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChickenQuerySet:
    def test_alive_excludes_deceased(self):
        alive = ChickenFactory(name="Alive", date_of_death=None)
        ChickenFactory(name="Dead", date_of_death=timezone.localdate())

        qs = Chicken.objects.alive()

        assert list(qs) == [alive]

    def test_deceased_excludes_alive(self):
        ChickenFactory(name="Alive", date_of_death=None)
        dead = ChickenFactory(name="Dead", date_of_death=timezone.localdate())

        qs = Chicken.objects.deceased()

        assert list(qs) == [dead]

    def test_alive_and_deceased_are_complementary(self):
        ChickenFactory(date_of_death=None)
        ChickenFactory(date_of_death=timezone.localdate())
        ChickenFactory(date_of_death=None)

        total = Chicken.objects.count()
        assert Chicken.objects.alive().count() + Chicken.objects.deceased().count() == total


@pytest.mark.django_db
class TestChickenDefaultOrdering:
    def test_chickens_are_ordered_by_name(self):
        ChickenFactory(name="Charlie")
        ChickenFactory(name="Alice")
        ChickenFactory(name="Bob")

        names = list(Chicken.objects.values_list("name", flat=True))

        assert names == ["Alice", "Bob", "Charlie"]


# ---------------------------------------------------------------------------
# Egg
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEggQuerySet:
    def test_saleable(self):
        saleable = EggFactory(quality=Egg.Quality.SALEABLE)
        EggFactory(quality=Egg.Quality.EDIBLE)
        EggFactory(quality=Egg.Quality.MESSY)

        assert list(Egg.objects.saleable()) == [saleable]

    def test_edible(self):
        EggFactory(quality=Egg.Quality.SALEABLE)
        edible = EggFactory(quality=Egg.Quality.EDIBLE)
        EggFactory(quality=Egg.Quality.MESSY)

        assert list(Egg.objects.edible()) == [edible]

    def test_messy(self):
        EggFactory(quality=Egg.Quality.SALEABLE)
        EggFactory(quality=Egg.Quality.EDIBLE)
        messy = EggFactory(quality=Egg.Quality.MESSY)

        assert list(Egg.objects.messy()) == [messy]

    def test_laid_on_specific_date(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        egg_today = EggFactory(
            laid_at=timezone.make_aware(
                timezone.datetime.combine(today, timezone.datetime.min.time())
            )
        )
        EggFactory(
            laid_at=timezone.make_aware(
                timezone.datetime.combine(yesterday, timezone.datetime.min.time())
            )
        )

        assert list(Egg.objects.laid_on(today)) == [egg_today]

    def test_laid_between_is_inclusive(self):
        today = timezone.localdate()
        two_days_ago = today - timedelta(days=2)
        three_days_ago = today - timedelta(days=3)

        def _at(d):
            return timezone.make_aware(timezone.datetime.combine(d, timezone.datetime.min.time()))

        inside_start = EggFactory(laid_at=_at(two_days_ago))
        inside_end = EggFactory(laid_at=_at(today))
        outside = EggFactory(laid_at=_at(three_days_ago))

        result = Egg.objects.laid_between(two_days_ago, today)

        assert set(result) == {inside_start, inside_end}
        assert outside not in result


@pytest.mark.django_db
class TestEggDefaultOrdering:
    def test_eggs_ordered_by_laid_at_desc(self):
        now = timezone.now()
        older = EggFactory(laid_at=now - timedelta(hours=2))
        newer = EggFactory(laid_at=now - timedelta(hours=1))
        newest = EggFactory(laid_at=now)

        assert list(Egg.objects.all()) == [newest, newer, older]


# ---------------------------------------------------------------------------
# NestingBoxPresencePeriod
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNestingBoxPresencePeriodQuerySet:
    def test_ended_since(self):
        cutoff = timezone.now() - timedelta(minutes=30)
        before = NestingBoxPresencePeriodFactory(
            started_at=timezone.now() - timedelta(hours=2),
            ended_at=timezone.now() - timedelta(hours=1),
        )
        after = NestingBoxPresencePeriodFactory(
            started_at=timezone.now() - timedelta(minutes=15),
            ended_at=timezone.now() - timedelta(minutes=5),
        )

        result = NestingBoxPresencePeriod.objects.ended_since(cutoff)

        assert after in result
        assert before not in result

    def test_for_box(self):
        box1 = NestingBoxFactory(name="one")
        box2 = NestingBoxFactory(name="two")
        p1 = NestingBoxPresencePeriodFactory(nesting_box=box1)
        NestingBoxPresencePeriodFactory(nesting_box=box2)

        assert list(NestingBoxPresencePeriod.objects.for_box(box1)) == [p1]

    def test_overlapping_matches_interior_and_partial(self):
        """overlapping(start, end) returns periods whose interval
        intersects [start, end]."""
        anchor = timezone.now().replace(microsecond=0)
        # The window we're querying for
        q_start = anchor
        q_end = anchor + timedelta(hours=1)

        # Period fully inside: should match
        inside = NestingBoxPresencePeriodFactory(
            started_at=anchor + timedelta(minutes=10),
            ended_at=anchor + timedelta(minutes=20),
        )
        # Period straddling the start: should match
        straddle_start = NestingBoxPresencePeriodFactory(
            started_at=anchor - timedelta(minutes=10),
            ended_at=anchor + timedelta(minutes=5),
        )
        # Period straddling the end: should match
        straddle_end = NestingBoxPresencePeriodFactory(
            started_at=anchor + timedelta(minutes=50),
            ended_at=anchor + timedelta(hours=2),
        )
        # Period entirely before: should not match
        outside_before = NestingBoxPresencePeriodFactory(
            started_at=anchor - timedelta(hours=2),
            ended_at=anchor - timedelta(minutes=1),
        )
        # Period entirely after: should not match
        outside_after = NestingBoxPresencePeriodFactory(
            started_at=anchor + timedelta(hours=2),
            ended_at=anchor + timedelta(hours=3),
        )

        result = set(NestingBoxPresencePeriod.objects.overlapping(q_start, q_end))

        assert result == {inside, straddle_start, straddle_end}
        assert outside_before not in result
        assert outside_after not in result


@pytest.mark.django_db
class TestNestingBoxPresencePeriodDefaultOrdering:
    def test_periods_ordered_by_started_at_desc(self):
        now = timezone.now()
        older = NestingBoxPresencePeriodFactory(
            started_at=now - timedelta(hours=2), ended_at=now - timedelta(hours=2)
        )
        newer = NestingBoxPresencePeriodFactory(
            started_at=now - timedelta(hours=1), ended_at=now - timedelta(hours=1)
        )

        assert list(NestingBoxPresencePeriod.objects.all()) == [newer, older]


# ---------------------------------------------------------------------------
# HardwareSensor
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHardwareSensorQuerySet:
    def test_online(self):
        from web_app.models import HardwareSensor

        online = HardwareSensorFactory()
        HardwareSensorFactory(offline=True)
        HardwareSensorFactory(degraded=True)

        assert list(HardwareSensor.objects.online()) == [online]

    def test_offline(self):
        from web_app.models import HardwareSensor

        HardwareSensorFactory()
        offline = HardwareSensorFactory(offline=True)

        assert list(HardwareSensor.objects.offline()) == [offline]

    def test_degraded(self):
        from web_app.models import HardwareSensor

        HardwareSensorFactory()
        HardwareSensorFactory(offline=True)
        degraded = HardwareSensorFactory(degraded=True)

        assert list(HardwareSensor.objects.degraded()) == [degraded]


# ---------------------------------------------------------------------------
# NestingBoxImage
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNestingBoxImageQuerySet:
    def test_far_from_events_deletes_orphan_images(self):
        """An image with no nearby presence period or egg is flagged
        for deletion by ``far_from_events``."""
        from web_app.models import NestingBoxImage

        anchor = timezone.now().replace(microsecond=0)

        # Orphan image: no presence or egg within window
        orphan = NestingBoxImageFactory(created_at=anchor)

        # Image near an egg: kept
        near_egg_ts = anchor + timedelta(days=1)
        EggFactory(laid_at=near_egg_ts)
        near_egg_image = NestingBoxImageFactory(created_at=near_egg_ts + timedelta(seconds=5))

        # Image near a period: kept
        near_period_ts = anchor + timedelta(days=2)
        NestingBoxPresencePeriodFactory(
            started_at=near_period_ts,
            ended_at=near_period_ts + timedelta(minutes=1),
        )
        near_period_image = NestingBoxImageFactory(
            created_at=near_period_ts + timedelta(seconds=10)
        )

        result = set(NestingBoxImage.objects.far_from_events(timedelta(seconds=30)))

        assert result == {orphan}
        assert near_egg_image not in result
        assert near_period_image not in result

    def test_far_from_events_empty_window(self):
        """With a large enough window, every image sits near some
        event and nothing is flagged."""
        from web_app.models import NestingBoxImage

        anchor = timezone.now()
        EggFactory(laid_at=anchor)
        NestingBoxImageFactory(created_at=anchor + timedelta(seconds=10))

        # 1-hour window easily covers the egg
        result = NestingBoxImage.objects.far_from_events(timedelta(hours=1))

        assert list(result) == []
