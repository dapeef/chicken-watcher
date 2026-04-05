import factory
from django.utils import timezone
from web_app.models import (
    Tag,
    Chicken,
    NestingBox,
    Egg,
    NestingBoxPresence,
    HardwareSensor,
    NestingBoxImage,
    NestingBoxPresencePeriod,
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
        lambda: timezone.now().date() - timezone.timedelta(days=365)
    )
    tag = factory.SubFactory(TagFactory)


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
    dud = False


class NestingBoxPresenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NestingBoxPresence

    chicken = factory.SubFactory(ChickenFactory)
    nesting_box = factory.SubFactory(NestingBoxFactory)
    present_at = factory.LazyFunction(timezone.now)


class NestingBoxPresencePeriodFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NestingBoxPresencePeriod

    chicken = factory.SubFactory(ChickenFactory)
    nesting_box = factory.SubFactory(NestingBoxFactory)
    started_at = factory.LazyFunction(timezone.now)
    ended_at = factory.LazyFunction(timezone.now)


class HardwareSensorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = HardwareSensor

    name = factory.Sequence(lambda n: f"sensor_{n}")
    is_connected = True


class NestingBoxImageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NestingBoxImage

    created_at = factory.LazyFunction(timezone.now)
    image = factory.django.ImageField(color="blue")
