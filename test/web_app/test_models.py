from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from web_app.models import NestingBoxPresence, NestingBoxPresencePeriod

from .factories import (
    ChickenFactory,
    EggFactory,
    HardwareSensorFactory,
    NestingBoxFactory,
    NestingBoxImageFactory,
    NestingBoxPresencePeriodFactory,
    TagFactory,
)


@pytest.mark.django_db
class TestChickenModel:
    def test_chicken_age(self):
        dob = date.today() - timedelta(days=100)
        chicken = ChickenFactory(date_of_birth=dob)
        assert chicken.age == 100

    def test_chicken_age_with_death(self):
        dob = date.today() - timedelta(days=100)
        dod = date.today() - timedelta(days=20)
        chicken = ChickenFactory(date_of_birth=dob, date_of_death=dod)
        assert chicken.age == 80

    def test_str(self):
        chicken = ChickenFactory(name="Bertha")
        assert str(chicken) == "Bertha"


@pytest.mark.django_db
class TestChickenTagUniqueness:
    """The unique_tag_per_live_chicken partial UniqueConstraint ensures a
    tag is held by at most one *live* chicken at a time. Dead chickens
    retain their tag for provenance (they're excluded from the
    constraint), so tags can be legitimately reassigned after death."""

    def test_two_live_chickens_cannot_share_a_tag(self):
        tag = TagFactory()
        ChickenFactory(name="Henrietta", tag=tag)
        with pytest.raises(IntegrityError), transaction.atomic():
            ChickenFactory(name="Henrietta II", tag=tag)

    def test_dead_chicken_and_live_chicken_can_share_a_tag(self):
        """When a chicken dies, its tag can be reassigned to a new live
        chicken. The dead chicken keeps the historical tag record."""
        tag = TagFactory()
        dead = ChickenFactory(
            name="Old Hen",
            tag=tag,
            date_of_death=date.today() - timedelta(days=7),
        )
        new = ChickenFactory(name="New Hen", tag=tag)
        assert dead.tag == tag
        assert new.tag == tag

    def test_multiple_dead_chickens_can_share_a_tag(self):
        """Historical data: several chickens held the same tag in
        succession, all of whom are now dead. All valid."""
        tag = TagFactory()
        ChickenFactory(name="First", tag=tag, date_of_death=date.today() - timedelta(days=30))
        ChickenFactory(name="Second", tag=tag, date_of_death=date.today() - timedelta(days=7))

    def test_multiple_live_chickens_can_have_null_tag(self):
        """The partial constraint only applies when tag IS NOT NULL, so
        many untagged chickens are allowed."""
        ChickenFactory(name="Henrietta", tag=None)
        ChickenFactory(name="Bertha", tag=None)
        # No exception

    def test_live_chicken_cannot_take_live_chickens_tag(self):
        """Reassigning a live chicken's tag to another live chicken is
        rejected (must kill the first chicken or unassign first)."""
        tag = TagFactory()
        ChickenFactory(name="Owner", tag=tag)
        new = ChickenFactory(name="Thief", tag=None)
        new.tag = tag
        with pytest.raises(IntegrityError), transaction.atomic():
            new.save()


@pytest.mark.django_db
class TestNestingBoxModel:
    def test_str_capitalises_name(self):
        assert str(NestingBoxFactory(name="left")) == "Left"

    def test_str_title_cases_multi_word_name(self):
        assert str(NestingBoxFactory(name="north nest")) == "North Nest"


@pytest.mark.django_db
class TestEggModel:
    def test_str(self):
        chicken = ChickenFactory(name="Bertha")
        box = NestingBoxFactory(name="Box A")
        laid_at = timezone.now().replace(year=2024, month=5, day=20, hour=10, minute=30)
        egg = EggFactory(chicken=chicken, nesting_box=box, laid_at=laid_at)
        assert str(egg) == "Bertha in Box A box at 2024-05-20 10:30"

    def test_str_unknown(self):
        egg = EggFactory(chicken=None, nesting_box=None)
        assert "Unknown chicken" in str(egg)
        assert "unknown box" in str(egg)

    def test_deleting_chicken_preserves_eggs_with_null_chicken(self):
        """Egg.chicken uses on_delete=SET_NULL to preserve historical records."""
        chicken = ChickenFactory(name="Bertha")
        box = NestingBoxFactory(name="Box A")
        egg = EggFactory(chicken=chicken, nesting_box=box)
        egg_id = egg.pk

        chicken.delete()

        egg.refresh_from_db()
        assert egg.pk == egg_id, "Egg should still exist after chicken deletion"
        assert egg.chicken is None
        assert egg.nesting_box == box, "Other FK should be unaffected"

    def test_deleting_nesting_box_preserves_eggs_with_null_box(self):
        """Egg.nesting_box uses on_delete=SET_NULL to preserve historical records."""
        chicken = ChickenFactory(name="Bertha")
        box = NestingBoxFactory(name="Box A")
        egg = EggFactory(chicken=chicken, nesting_box=box)
        egg_id = egg.pk

        box.delete()

        egg.refresh_from_db()
        assert egg.pk == egg_id, "Egg should still exist after nesting box deletion"
        assert egg.nesting_box is None
        assert egg.chicken == chicken, "Other FK should be unaffected"


@pytest.mark.django_db
class TestNestingBoxPresencePeriodConstraints:
    """The started_at <= ended_at CheckConstraint was in the original
    NestingBoxVisit schema (migration 0001) but dropped accidentally when
    the model was renamed in 0011. Restored in migration 0023."""

    def test_well_ordered_period_saves(self):
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            started_at=now, ended_at=now + timedelta(minutes=5)
        )
        assert period.pk is not None

    def test_equal_timestamps_are_allowed(self):
        """A point-in-time presence (started == ended) is a legitimate
        state and must be permitted; only 'ends before it starts' is a
        violation."""
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(started_at=now, ended_at=now)
        assert period.pk is not None

    def test_ended_before_started_is_rejected(self):
        """Direct creation of an inverted period must raise IntegrityError."""
        now = timezone.now()
        chicken = ChickenFactory()
        box = NestingBoxFactory()
        with pytest.raises(IntegrityError), transaction.atomic():
            NestingBoxPresencePeriod.objects.create(
                chicken=chicken,
                nesting_box=box,
                started_at=now,
                ended_at=now - timedelta(seconds=1),
            )

    def test_updating_ended_at_backwards_is_rejected(self):
        """Updating an existing row to violate the invariant must fail."""
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            started_at=now, ended_at=now + timedelta(minutes=5)
        )
        period.ended_at = now - timedelta(minutes=5)
        with pytest.raises(IntegrityError), transaction.atomic():
            period.save(update_fields=["ended_at"])


@pytest.mark.django_db
class TestNestingBoxPresenceModel:
    def test_str(self):
        chicken = ChickenFactory(name="Bertha")
        box = NestingBoxFactory(name="Box A")
        presence = NestingBoxPresence.objects.create(chicken=chicken, nesting_box=box)
        assert "Bertha" in str(presence)
        assert "Box A" in str(presence)


@pytest.mark.django_db
class TestHardwareSensorModel:
    def test_str_online(self):
        sensor = HardwareSensorFactory(name="rfid_1", is_connected=True)
        assert str(sensor) == "rfid_1 (Online)"

    def test_str_offline(self):
        sensor = HardwareSensorFactory(name="rfid_1", is_connected=False)
        assert str(sensor) == "rfid_1 (Offline)"


@pytest.mark.django_db
class TestNestingBoxImageModel:
    def test_str(self):
        image = NestingBoxImageFactory()
        assert "Image taken at" in str(image)
