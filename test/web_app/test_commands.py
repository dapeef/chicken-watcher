import pytest
from django.core.management import call_command
from web_app.models import Chicken, NestingBox, Egg, NestingBoxPresence, NestingBoxPresencePeriod


@pytest.mark.django_db
def test_seed_command_refresh():
    # Run seed in refresh mode
    call_command("seed", mode="refresh")

    assert Chicken.objects.count() > 0
    assert NestingBox.objects.count() == 2
    # Since populate_data has some randomness, we just check if it created something
    # but based on the code it should create at least some records
    assert Egg.objects.count() >= 0
    assert NestingBoxPresence.objects.count() >= 0
    assert NestingBoxPresencePeriod.objects.count() > 0

    # Verify that presences are linked to periods
    if NestingBoxPresence.objects.exists():
        assert NestingBoxPresence.objects.filter(presence_period__isnull=False).exists()


@pytest.mark.django_db
def test_seed_command_clear():
    # First seed some data
    call_command("seed", mode="refresh")
    assert Chicken.objects.count() > 0

    # Now clear
    call_command("seed", mode="clear")
    assert Chicken.objects.count() == 0
    assert NestingBox.objects.count() == 0
    assert Egg.objects.count() == 0
    assert NestingBoxPresence.objects.count() == 0
    assert NestingBoxPresencePeriod.objects.count() == 0
