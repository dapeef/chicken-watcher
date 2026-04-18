from datetime import timedelta

import factory
from django.utils import timezone

from web_app.models import (
    Chicken,
    Egg,
    HardwareSensor,
    NestingBox,
    NestingBoxImage,
    NestingBoxPresence,
    NestingBoxPresencePeriod,
    Tag,
)


class TagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tag

    rfid_string = factory.Sequence(lambda n: f"TAG_{n:010d}")
    number = factory.Sequence(lambda n: n + 1)


class ChickenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Chicken

    name = factory.Faker("name")
    date_of_birth = factory.LazyFunction(
        # Use localdate() (not .date() on now()) so tests near UTC midnight
        # get the correct local date rather than the UTC date.
        lambda: timezone.localdate() - timedelta(days=365)
    )
    tag = factory.SubFactory(TagFactory)

    class Params:
        deceased = factory.Trait(
            date_of_death=factory.LazyFunction(timezone.localdate),
        )
        untagged = factory.Trait(tag=None)


class NestingBoxFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NestingBox

    name = factory.Sequence(lambda n: f"Box {n}")


class EggFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Egg

    chicken = factory.SubFactory(ChickenFactory)
    nesting_box = factory.SubFactory(NestingBoxFactory)
    laid_at = factory.LazyFunction(timezone.now)
    quality = Egg.Quality.SALEABLE

    class Params:
        edible = factory.Trait(quality=Egg.Quality.EDIBLE)
        messy = factory.Trait(quality=Egg.Quality.MESSY)


class NestingBoxPresenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NestingBoxPresence

    chicken = factory.SubFactory(ChickenFactory)
    nesting_box = factory.SubFactory(NestingBoxFactory)
    present_at = factory.LazyFunction(timezone.now)
    sensor_id = ""


class NestingBoxPresencePeriodFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NestingBoxPresencePeriod

    chicken = factory.SubFactory(ChickenFactory)
    nesting_box = factory.SubFactory(NestingBoxFactory)
    started_at = factory.LazyFunction(timezone.now)
    # Default to a 5-minute visit rather than a zero-duration period.
    # Zero-duration periods are technically valid (started == ended is
    # allowed by the check constraint) but misleading in tests that
    # care about duration. Use started_at + 5m for a realistic default.
    ended_at = factory.LazyAttribute(lambda o: o.started_at + timedelta(minutes=5))

    class Params:
        long_visit = factory.Trait(
            ended_at=factory.LazyAttribute(lambda o: o.started_at + timedelta(hours=1)),
        )


class HardwareSensorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HardwareSensor

    name = factory.Sequence(lambda n: f"sensor_{n}")
    is_connected = True

    class Params:
        offline = factory.Trait(is_connected=False)


class NestingBoxImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NestingBoxImage

    created_at = factory.LazyFunction(timezone.now)
    image = factory.django.ImageField(color="blue")
