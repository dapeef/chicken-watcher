import pytest
from django.core.management import call_command
from web_app.models import NestingBoxImage
from test.web_app.factories import NestingBoxImageFactory


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
