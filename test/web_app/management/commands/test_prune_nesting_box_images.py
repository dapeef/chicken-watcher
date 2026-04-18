import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from test.web_app.factories import (
    EggFactory,
    NestingBoxImageFactory,
    NestingBoxPresencePeriodFactory,
)
from web_app.models import NestingBoxImage

# ---------------------------------------------------------------------------
# Nesting box presence period proximity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prune_images_deletes_images_with_no_nearby_events():
    """Images with no presence period or egg within 30s should be deleted."""
    NestingBoxImageFactory(created_at=timezone.now())
    assert NestingBoxImage.objects.count() == 1

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_prune_images_keeps_image_within_30s_before_period_start():
    """An image created 29s before a period starts should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    NestingBoxPresencePeriodFactory(
        started_at=now + datetime.timedelta(seconds=29),
        ended_at=now + datetime.timedelta(seconds=60),
    )

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_keeps_image_within_30s_after_period_end():
    """An image created 29s after a period ends should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    NestingBoxPresencePeriodFactory(
        started_at=now - datetime.timedelta(seconds=60),
        ended_at=now - datetime.timedelta(seconds=29),
    )

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_keeps_image_during_period():
    """An image whose timestamp falls inside a period should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    NestingBoxPresencePeriodFactory(
        started_at=now - datetime.timedelta(seconds=30),
        ended_at=now + datetime.timedelta(seconds=30),
    )

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_deletes_image_just_outside_30s_window():
    """An image 31s before a period starts should be deleted."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    NestingBoxPresencePeriodFactory(
        started_at=now + datetime.timedelta(seconds=31),
        ended_at=now + datetime.timedelta(seconds=90),
    )

    call_command("prune_nesting_box_images")

    assert not NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_mixed_keeps_and_deletes():
    """Only images near a presence period are kept; others are removed."""
    now = timezone.now()
    close_image = NestingBoxImageFactory(created_at=now)
    far_image = NestingBoxImageFactory(created_at=now + datetime.timedelta(minutes=10))
    # Period is only near the first image
    NestingBoxPresencePeriodFactory(
        started_at=now - datetime.timedelta(seconds=5),
        ended_at=now + datetime.timedelta(seconds=5),
    )

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=close_image.pk).exists()
    assert not NestingBoxImage.objects.filter(pk=far_image.pk).exists()


@pytest.mark.django_db
def test_prune_images_when_no_images_exist():
    """Running the command with no images should not raise an error."""
    NestingBoxPresencePeriodFactory()
    assert NestingBoxImage.objects.count() == 0

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_prune_images_when_no_presences_exist():
    """With no presence periods all images should be deleted."""
    NestingBoxImageFactory.create_batch(3)
    assert NestingBoxImage.objects.count() == 3

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_prune_images_deletes_image_files(mocker):
    """The underlying image file on disk should be deleted for pruned images."""
    NestingBoxImageFactory(created_at=timezone.now())
    # No presence period or egg, so the image should be pruned
    mock_delete = mocker.patch("django.db.models.fields.files.FieldFile.delete")

    call_command("prune_nesting_box_images")

    mock_delete.assert_called_once_with(False)


@pytest.mark.django_db
def test_prune_images_does_not_delete_files_for_kept_images(mocker):
    """Image files for kept images should not be deleted."""
    now = timezone.now()
    NestingBoxImageFactory(created_at=now)
    NestingBoxPresencePeriodFactory(
        started_at=now - datetime.timedelta(seconds=5),
        ended_at=now + datetime.timedelta(seconds=5),
    )
    mock_delete = mocker.patch("django.db.models.fields.files.FieldFile.delete")

    call_command("prune_nesting_box_images")

    mock_delete.assert_not_called()


# ---------------------------------------------------------------------------
# Egg proximity
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prune_images_keeps_image_within_30s_before_egg():
    """An image created 29s before an egg should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    EggFactory(laid_at=now + datetime.timedelta(seconds=29))

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_keeps_image_within_30s_after_egg():
    """An image created 29s after an egg should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    EggFactory(laid_at=now - datetime.timedelta(seconds=29))

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_keeps_image_exactly_at_egg():
    """An image with the same timestamp as an egg should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    EggFactory(laid_at=now)

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_deletes_image_just_outside_30s_egg_window():
    """An image 31s away from any egg should be deleted (no presence either)."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    EggFactory(laid_at=now + datetime.timedelta(seconds=31))

    call_command("prune_nesting_box_images")

    assert not NestingBoxImage.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
def test_prune_images_kept_by_egg_when_no_nearby_period():
    """An image near an egg but far from any presence period should be kept."""
    now = timezone.now()
    image = NestingBoxImageFactory(created_at=now)
    EggFactory(laid_at=now + datetime.timedelta(seconds=10))
    # Period is far away
    NestingBoxPresencePeriodFactory(
        started_at=now + datetime.timedelta(minutes=5),
        ended_at=now + datetime.timedelta(minutes=6),
    )

    call_command("prune_nesting_box_images")

    assert NestingBoxImage.objects.filter(pk=image.pk).exists()
