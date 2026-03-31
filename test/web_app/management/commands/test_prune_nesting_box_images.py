import datetime
import pytest
from django.core.management import call_command
from django.utils import timezone
from web_app.models import NestingBoxImage
from test.web_app.factories import NestingBoxImageFactory, NestingBoxPresenceFactory



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
