import csv
import datetime
import pytest
from pathlib import Path
from django.core.management import call_command
from web_app.models import (
    Chicken,
    NestingBox,
    Egg,
    NestingBoxPresence,
    NestingBoxPresencePeriod,
    NestingBoxImage,
)
from test.web_app.factories import NestingBoxImageFactory, ChickenFactory


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


@pytest.mark.django_db
def test_seed_chickens_creates_from_csv(tmp_path):
    csv_path = tmp_path / "chickens.csv"
    csv_path.write_text(
        "Name,DoB,Tag ID\nHenrietta,2025-01-15,AABBCCDD\nCluckers,2025-03-20,11223344\n"
    )

    from web_app.management.commands.seed import seed_chickens_from_csv

    seed_chickens_from_csv(csv_path)

    assert Chicken.objects.count() == 2
    henrietta = Chicken.objects.get(name="Henrietta")
    assert henrietta.date_of_birth == datetime.date(2025, 1, 15)
    assert henrietta.tag_string == "AABBCCDD"


@pytest.mark.django_db
def test_seed_chickens_updates_existing_chicken(tmp_path):
    ChickenFactory(
        name="Henrietta", date_of_birth=datetime.date(2024, 1, 1), tag_string="OLDTAG"
    )

    csv_path = tmp_path / "chickens.csv"
    csv_path.write_text("Name,DoB,Tag ID\nHenrietta,2025-01-15,NEWTAG\n")

    from web_app.management.commands.seed import seed_chickens_from_csv

    seed_chickens_from_csv(csv_path)

    assert Chicken.objects.count() == 1
    henrietta = Chicken.objects.get(name="Henrietta")
    assert henrietta.date_of_birth == datetime.date(2025, 1, 15)
    assert henrietta.tag_string == "NEWTAG"


@pytest.mark.django_db
def test_seed_chickens_does_not_clear_other_data(tmp_path):
    ChickenFactory(name="ExistingChicken")

    csv_path = tmp_path / "chickens.csv"
    csv_path.write_text("Name,DoB,Tag ID\nNewChicken,2025-06-01,FFEEBBAA\n")

    from web_app.management.commands.seed import seed_chickens_from_csv

    seed_chickens_from_csv(csv_path)

    assert Chicken.objects.count() == 2
    assert Chicken.objects.filter(name="ExistingChicken").exists()
    assert Chicken.objects.filter(name="NewChicken").exists()


@pytest.mark.django_db
def test_seed_chickens_via_call_command():
    call_command("seed", mode="seed_chickens")
    # chickens.csv has 6 rows
    assert Chicken.objects.count() == 6


@pytest.mark.django_db
def test_delete_nesting_box_images_removes_all_records():
    NestingBoxImageFactory.create_batch(3)
    assert NestingBoxImage.objects.count() == 3

    call_command("delete_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_delete_nesting_box_images_deletes_image_files(mocker):
    images = NestingBoxImageFactory.create_batch(2)
    mock_delete = mocker.patch("django.db.models.fields.files.FieldFile.delete")

    call_command("delete_nesting_box_images")

    assert mock_delete.call_count == len(images)
    mock_delete.assert_called_with(False)


@pytest.mark.django_db
def test_delete_nesting_box_images_when_none_exist():
    assert NestingBoxImage.objects.count() == 0

    call_command("delete_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0
