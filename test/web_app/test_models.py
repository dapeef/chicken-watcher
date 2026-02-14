import pytest
from datetime import date, timedelta
from django.utils import timezone
from web_app.models import Chicken, NestingBoxPresence
from .factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
    HardwareSensorFactory,
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
class TestNestingBoxModel:
    def test_str(self):
        box = NestingBoxFactory(name="Box A")
        assert str(box) == "Box A"


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
class TestChickenQuerySet:
    def test_with_egg_metrics(self):
        chicken = ChickenFactory()
        # Create 3 eggs within the last 30 days
        now = timezone.now()
        EggFactory.create_batch(3, chicken=chicken, laid_at=now - timedelta(days=5))
        # Create 1 egg outside the last 30 days
        EggFactory(chicken=chicken, laid_at=now - timedelta(days=40))

        # We need to re-query with the manager's with_egg_metrics
        annotated_chicken = Chicken.objects.with_egg_metrics(days=30).get(pk=chicken.pk)

        assert annotated_chicken.eggs_window == 3
        # 3 eggs / 30 days = 0.1
        assert annotated_chicken.eggs_per_day == pytest.approx(0.1)

    def test_with_egg_metrics_no_eggs(self):
        chicken = ChickenFactory()
        annotated_chicken = Chicken.objects.with_egg_metrics(days=30).get(pk=chicken.pk)
        assert annotated_chicken.eggs_window == 0
        assert annotated_chicken.eggs_per_day == 0.0
