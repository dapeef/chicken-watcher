import datetime

import pytest
from django.core.management import call_command

from test.web_app.factories import (
    ChickenFactory,
    NestingBoxFactory,
    TagFactory,
)
from web_app.models import (
    Chicken,
    Egg,
    NestingBox,
    NestingBoxPresence,
    NestingBoxPresencePeriod,
    Tag,
)


@pytest.mark.django_db
def test_seed_command_spawn_test_data(settings):
    settings.DEBUG = True  # required by the dev-mode guard
    call_command("seed", mode="spawn_test_data", yes=True)

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
def test_seed_command_clear(settings):
    settings.DEBUG = True  # spawn_test_data requires DEBUG=True
    call_command("seed", mode="spawn_test_data", yes=True)
    assert Chicken.objects.count() > 0

    call_command("seed", mode="clear", yes=True)
    assert Chicken.objects.count() == 0
    assert Tag.objects.count() == 0
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


# ---------------------------------------------------------------------------
# Tag seeding tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_tags_creates_from_csv(tmp_path):
    csv_path = tmp_path / "tags.csv"
    csv_path.write_text("Tag number,Tag ID\n1,AABBCCDD\n2,11223344\n")

    from web_app.management.commands.seed import seed_tags_from_csv

    seed_tags_from_csv(csv_path)

    assert Tag.objects.count() == 2
    tag1 = Tag.objects.get(number=1)
    assert tag1.rfid_string == "AABBCCDD"
    tag2 = Tag.objects.get(number=2)
    assert tag2.rfid_string == "11223344"


@pytest.mark.django_db
def test_seed_tags_updates_existing_tag(tmp_path):
    TagFactory(number=1, rfid_string="OLDSTRING")

    csv_path = tmp_path / "tags.csv"
    csv_path.write_text("Tag number,Tag ID\n1,NEWSTRING\n")

    from web_app.management.commands.seed import seed_tags_from_csv

    seed_tags_from_csv(csv_path)

    assert Tag.objects.count() == 1
    tag = Tag.objects.get(number=1)
    assert tag.rfid_string == "NEWSTRING"


@pytest.mark.django_db
def test_seed_tags_is_idempotent(tmp_path):
    csv_path = tmp_path / "tags.csv"
    csv_path.write_text("Tag number,Tag ID\n1,AABBCCDD\n")

    from web_app.management.commands.seed import seed_tags_from_csv

    seed_tags_from_csv(csv_path)
    seed_tags_from_csv(csv_path)

    assert Tag.objects.count() == 1


@pytest.mark.django_db
def test_seed_tags_does_not_clear_other_data(tmp_path):
    TagFactory(number=99, rfid_string="EXISTING")

    csv_path = tmp_path / "tags.csv"
    csv_path.write_text("Tag number,Tag ID\n1,AABBCCDD\n")

    from web_app.management.commands.seed import seed_tags_from_csv

    seed_tags_from_csv(csv_path)

    assert Tag.objects.filter(number=99).exists()
    assert Tag.objects.filter(number=1).exists()


@pytest.mark.django_db
def test_seed_tags_via_call_command(tmp_path):
    csv_path = tmp_path / "tags.csv"
    csv_path.write_text("Tag number,Tag ID\n1,AABBCCDD\n2,11223344\n3,DEADBEEF\n")
    call_command("seed", mode="seed_tags", tags_csv_file=str(csv_path))
    assert Tag.objects.count() == 3


# ---------------------------------------------------------------------------
# Chicken seeding tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_chickens_creates_from_csv(tmp_path):
    # Tags must exist before seeding chickens
    TagFactory(number=1, rfid_string="AABBCCDD")
    TagFactory(number=2, rfid_string="11223344")

    csv_path = tmp_path / "chickens.csv"
    csv_path.write_text(
        "Name,DoB,Tag number\nHenrietta,2025-01-15,1\nCluckers,2025-03-20,2\n"
    )

    from web_app.management.commands.seed import seed_chickens_from_csv

    seed_chickens_from_csv(csv_path)

    assert Chicken.objects.count() == 2
    henrietta = Chicken.objects.get(name="Henrietta")
    assert henrietta.date_of_birth == datetime.date(2025, 1, 15)
    assert henrietta.tag.number == 1
    assert henrietta.tag.rfid_string == "AABBCCDD"


@pytest.mark.django_db
def test_seed_chickens_updates_existing_chicken(tmp_path):
    old_tag = TagFactory(number=1, rfid_string="OLDTAG")
    new_tag = TagFactory(number=2, rfid_string="NEWTAG")
    ChickenFactory(
        name="Henrietta", date_of_birth=datetime.date(2024, 1, 1), tag=old_tag
    )

    csv_path = tmp_path / "chickens.csv"
    csv_path.write_text("Name,DoB,Tag number\nHenrietta,2025-01-15,2\n")

    from web_app.management.commands.seed import seed_chickens_from_csv

    seed_chickens_from_csv(csv_path)

    assert Chicken.objects.count() == 1
    henrietta = Chicken.objects.get(name="Henrietta")
    assert henrietta.date_of_birth == datetime.date(2025, 1, 15)
    assert henrietta.tag == new_tag


@pytest.mark.django_db
def test_seed_chickens_skips_missing_tag(tmp_path, caplog):
    import logging

    csv_path = tmp_path / "chickens.csv"
    # Tag number 99 does not exist
    csv_path.write_text("Name,DoB,Tag number\nHenrietta,2025-01-15,99\n")

    from web_app.management.commands.seed import seed_chickens_from_csv

    with caplog.at_level(logging.WARNING, logger="web_app.management.commands.seed"):
        seed_chickens_from_csv(csv_path)

    assert Chicken.objects.count() == 0
    assert any("No Tag found with number 99" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_seed_chickens_does_not_clear_other_data(tmp_path):
    ChickenFactory(name="ExistingChicken")

    TagFactory(number=1, rfid_string="FFEEBBAA")
    csv_path = tmp_path / "chickens.csv"
    csv_path.write_text("Name,DoB,Tag number\nNewChicken,2025-06-01,1\n")

    from web_app.management.commands.seed import seed_chickens_from_csv

    seed_chickens_from_csv(csv_path)

    assert Chicken.objects.count() == 2
    assert Chicken.objects.filter(name="ExistingChicken").exists()
    assert Chicken.objects.filter(name="NewChicken").exists()


@pytest.mark.django_db
def test_seed_chickens_via_call_command(tmp_path):
    # Create required tags
    for i, rfid in enumerate(
        ["AABBCCDD", "11223344", "DEADBEEF", "CAFEBABE", "00112233", "44556677"],
        start=1,
    ):
        TagFactory(number=i, rfid_string=rfid)

    csv_path = tmp_path / "chickens.csv"
    csv_path.write_text(
        "Name,DoB,Tag number\n"
        "Henrietta,2025-01-15,1\n"
        "Cluckers,2025-03-20,2\n"
        "Feathers,2025-05-10,3\n"
        "Nugget,2025-06-01,4\n"
        "Pecky,2025-07-04,5\n"
        "Fluffy,2025-08-08,6\n"
    )
    call_command("seed", mode="seed_chickens", csv_file=str(csv_path))
    assert Chicken.objects.count() == 6


# ---------------------------------------------------------------------------
# Destructive-mode guard tests
# ---------------------------------------------------------------------------


from django.core.management.base import CommandError  # noqa: E402


@pytest.mark.django_db
class TestDestructiveModeGuards:
    """Destructive seed modes (clear, spawn_test_data) must not run
    accidentally. Guards:

    - spawn_test_data requires DEBUG=True regardless of --yes.
    - clear and spawn_test_data require --yes (or interactive confirmation
      with 'yes') when invoked.
    - Non-interactive (no TTY) callers must use --yes.
    """

    def test_spawn_test_data_refuses_when_debug_false(self, settings, mocker):
        settings.DEBUG = False
        # Even with --yes, spawn_test_data must refuse.
        with pytest.raises(CommandError, match="DEBUG=True"):
            call_command("seed", mode="spawn_test_data", yes=True)
        assert Chicken.objects.count() == 0

    def test_clear_allowed_when_debug_false_with_yes(self, settings):
        """clear does not require DEBUG=True; it's a legitimate (if scary)
        operation in production. --yes is still required."""
        settings.DEBUG = False
        ChickenFactory()
        assert Chicken.objects.count() == 1

        call_command("seed", mode="clear", yes=True)

        assert Chicken.objects.count() == 0

    def test_clear_refuses_without_yes_in_non_interactive(self, mocker):
        mocker.patch("sys.stdin.isatty", return_value=False)
        ChickenFactory()

        with pytest.raises(CommandError, match="--yes"):
            call_command("seed", mode="clear")

        # Data untouched
        assert Chicken.objects.count() == 1

    def test_spawn_test_data_refuses_without_yes_in_non_interactive(
        self, mocker, settings
    ):
        """Even with DEBUG=True, spawn_test_data requires --yes when
        non-interactive. The DEBUG guard is layered on top of, not a
        replacement for, the confirmation guard."""
        settings.DEBUG = True  # pass the DEBUG check so we exercise the yes check
        mocker.patch("sys.stdin.isatty", return_value=False)

        with pytest.raises(CommandError, match="--yes"):
            call_command("seed", mode="spawn_test_data")

    def test_clear_interactive_proceeds_on_yes(self, mocker):
        mocker.patch("sys.stdin.isatty", return_value=True)
        mocker.patch("builtins.input", return_value="yes")
        ChickenFactory()

        call_command("seed", mode="clear")

        assert Chicken.objects.count() == 0

    def test_clear_interactive_aborts_on_other_input(self, mocker):
        mocker.patch("sys.stdin.isatty", return_value=True)
        mocker.patch("builtins.input", return_value="no")
        ChickenFactory()

        with pytest.raises(CommandError, match="Aborted"):
            call_command("seed", mode="clear")

        assert Chicken.objects.count() == 1

    def test_non_destructive_modes_need_no_confirmation(self, mocker):
        """seed_nesting_boxes, seed_tags, seed_chickens don't wipe anything
        and so must run without --yes or any prompt."""
        mocker.patch("sys.stdin.isatty", return_value=False)
        mock_input = mocker.patch("builtins.input")

        call_command("seed", mode="seed_nesting_boxes")

        assert mock_input.call_count == 0
        assert NestingBox.objects.count() == 2
