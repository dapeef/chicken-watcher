import pytest
from datetime import date, timedelta
from django.utils import timezone
from web_app.models import Chicken
from .factories import ChickenFactory, EggFactory

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
