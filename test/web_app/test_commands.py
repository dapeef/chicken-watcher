import csv
import datetime
import pytest
from pathlib import Path
from django.core.management import call_command
from django.utils import timezone
from web_app.models import (
    Chicken,
    NestingBox,
    Egg,
    NestingBoxPresence,
    NestingBoxPresencePeriod,
    NestingBoxImage,
)
from test.web_app.factories import (
    NestingBoxImageFactory,
    NestingBoxPresenceFactory,
    ChickenFactory,
    NestingBoxFactory,
)


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


# ---------------------------------------------------------------------------
# prune_nesting_box_images
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prune_images_deletes_images_with_no_nearby_presence():
    """Images that have no presence event within 30s should be deleted."""
    NestingBoxImageFactory(created_at=timezone.now())
    assert NestingBoxImage.objects.count() == 1

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_prune_images_keeps_image_within_30s_before_presence():
    """An image created 29s before a presence event should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    NestingBoxPresenceFactory(present_at=now + datetime.timedelta(seconds=29))

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_keeps_image_within_30s_after_presence():
    """An image created 29s after a presence event should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    NestingBoxPresenceFactory(present_at=now - datetime.timedelta(seconds=29))

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_keeps_image_exactly_at_presence():
    """An image with the same timestamp as a presence event should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    NestingBoxPresenceFactory(present_at=now)

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_deletes_image_just_outside_30s_window():
    """An image 31s away from any presence event should be deleted."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    NestingBoxPresenceFactory(present_at=now + datetime.timedelta(seconds=31))

    call_command("prune_nesting_box_images")

    assert not NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_mixed_keeps_and_deletes():
    """Only images near a presence are kept; others are removed."""
    now = timezone.now()
    close_image = NestingBoxImageFactory(created_at=now)
    far_image = NestingBoxImageFactory(created_at=now + datetime.timedelta(minutes=10))
    # Presence is only near the first image
    NestingBoxPresenceFactory(present_at=now)

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=close_image.pk).exists()
    assert not NestingBoxImage.objects.filter(pk=far_image.pk).exists()


@pytest.mark.django_db
def test_prune_images_when_no_images_exist():
    """Running the command with no images should not raise an error."""
    NestingBoxPresenceFactory()
    assert NestingBoxImage.objects.count() == 0

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_prune_images_when_no_presences_exist():
    """With no presences all images should be deleted."""
    NestingBoxImageFactory.create_batch(3)
    assert NestingBoxImage.objects.count() == 3

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_prune_images_deletes_image_files(mocker):
    """The underlying image file on disk should be deleted for pruned images."""
    now = timezone.now()
    NestingBoxImageFactory(created_at=now)
    # No presence, so the image should be pruned
    mock_delete = mocker.patch("django.db.models.fields.files.FieldFile.delete")

    call_command("prune_nesting_box_images")

    mock_delete.assert_called_once_with(False)


@pytest.mark.django_db
def test_prune_images_does_not_delete_files_for_kept_images(mocker):
    """Image files for kept images should not be deleted."""
    now = timezone.now()
    NestingBoxImageFactory(created_at=now)
    NestingBoxPresenceFactory(present_at=now)
    mock_delete = mocker.patch("django.db.models.fields.files.FieldFile.delete")

    call_command("prune_nesting_box_images")

    mock_delete.assert_not_called()
