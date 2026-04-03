import datetime
import pytest
from django.core.management import call_command
from web_app.models import (
    Chicken,
    NestingBox,
    Egg,
    NestingBoxPresence,
    NestingBoxPresencePeriod,
)
from test.web_app.factories import (
    ChickenFactory,
    NestingBoxFactory,
)


@pytest.mark.django_db
def test_seed_command_spawn_test_data():
    call_command("seed", mode="spawn_test_data")

    assert Chicken.objects.count() > 0
    assert NestingBox.objects.count() == 2
    assert Egg.objects.count() > 0
    assert NestingBoxPresencePeriod.objects.count() > 0

    # Seed must not create any raw NestingBoxPresence rows
    assert NestingBoxPresence.objects.count() == 0

    # Every period should be linked to a chicken and a nesting box
    assert not NestingBoxPresencePeriod.objects.filter(chicken__isnull=True).exists()
    assert not NestingBoxPresencePeriod.objects.filter(
        nesting_box__isnull=True
    ).exists()

    # Every period should have ended_at >= started_at
    from django.db.models import F

    assert not NestingBoxPresencePeriod.objects.filter(
        ended_at__lt=F("started_at")
    ).exists()


@pytest.mark.django_db
def test_seed_command_clear():
    call_command("seed", mode="spawn_test_data")
    assert Chicken.objects.count() > 0

    call_command("seed", mode="clear")
    assert Chicken.objects.count() == 0
    assert NestingBox.objects.count() == 0
    assert Egg.objects.count() == 0
    assert NestingBoxPresencePeriod.objects.count() == 0


@pytest.mark.django_db
def test_seed_nesting_boxes_creates_boxes():
    from web_app.management.commands.seed import seed_nesting_boxes

    seed_nesting_boxes()

    assert NestingBox.objects.count() == 2
    assert NestingBox.objects.filter(name="left").exists()
    assert NestingBox.objects.filter(name="right").exists()


@pytest.mark.django_db
def test_seed_nesting_boxes_is_idempotent():
    from web_app.management.commands.seed import seed_nesting_boxes

    seed_nesting_boxes()
    seed_nesting_boxes()

    assert NestingBox.objects.count() == 2


@pytest.mark.django_db
def test_seed_nesting_boxes_does_not_clear_other_data():
    NestingBoxFactory(name="extra")

    from web_app.management.commands.seed import seed_nesting_boxes

    seed_nesting_boxes()

    assert NestingBox.objects.filter(name="extra").exists()


@pytest.mark.django_db
def test_seed_nesting_boxes_via_call_command():
    call_command("seed", mode="seed_nesting_boxes")

    assert NestingBox.objects.count() == 2


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
def test_seed_chickens_via_call_command(tmp_path):
    csv_path = tmp_path / "chickens.csv"
    csv_path.write_text(
        "Name,DoB,Tag ID\n"
        "Henrietta,2025-01-15,AABBCCDD\n"
        "Cluckers,2025-03-20,11223344\n"
        "Feathers,2025-05-10,DEADBEEF\n"
        "Nugget,2025-06-01,CAFEBABE\n"
        "Pecky,2025-07-04,00112233\n"
        "Fluffy,2025-08-08,44556677\n"
    )
    call_command("seed", mode="seed_chickens", csv_file=str(csv_path))
    assert Chicken.objects.count() == 6
