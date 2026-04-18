"""
Tests for the ``--all`` mode of ``prune_nesting_box_images``.

These were previously in a separate ``test_delete_nesting_box_images.py``
file because the delete functionality lived in its own command. After
consolidation the tests are updated to call ``prune_nesting_box_images``
with ``--all`` (``delete_all=True``).
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from test.web_app.factories import NestingBoxImageFactory
from web_app.models import NestingBoxImage


@pytest.mark.django_db
def test_delete_all_removes_all_records():
    NestingBoxImageFactory.create_batch(3)
    assert NestingBoxImage.objects.count() == 3

    call_command("prune_nesting_box_images", delete_all=True, yes=True)

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_delete_all_deletes_image_files(mocker):
    images = NestingBoxImageFactory.create_batch(2)
    mock_delete = mocker.patch("django.db.models.fields.files.FieldFile.delete")

    call_command("prune_nesting_box_images", delete_all=True, yes=True)

    assert mock_delete.call_count == len(images)
    mock_delete.assert_called_with(False)


@pytest.mark.django_db
def test_delete_all_when_none_exist():
    assert NestingBoxImage.objects.count() == 0

    # No guard invoked when there's nothing to delete.
    call_command("prune_nesting_box_images", delete_all=True)

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_delete_all_refuses_without_yes_when_non_interactive(mocker):
    NestingBoxImageFactory.create_batch(2)
    mocker.patch("sys.stdin.isatty", return_value=False)

    with pytest.raises(CommandError, match="--yes"):
        call_command("prune_nesting_box_images", delete_all=True)

    assert NestingBoxImage.objects.count() == 2


@pytest.mark.django_db
def test_delete_all_prompts_interactively_and_proceeds_on_yes(mocker):
    NestingBoxImageFactory.create_batch(2)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("builtins.input", return_value="yes")

    call_command("prune_nesting_box_images", delete_all=True)

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_delete_all_prompts_interactively_and_aborts_on_other_input(mocker):
    NestingBoxImageFactory.create_batch(2)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("builtins.input", return_value="no")

    with pytest.raises(CommandError, match="Aborted"):
        call_command("prune_nesting_box_images", delete_all=True)

    assert NestingBoxImage.objects.count() == 2


@pytest.mark.django_db
def test_delete_all_yes_flag_bypasses_prompt(mocker):
    NestingBoxImageFactory.create_batch(2)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mock_input = mocker.patch("builtins.input")

    call_command("prune_nesting_box_images", delete_all=True, yes=True)

    assert mock_input.call_count == 0
    assert NestingBoxImage.objects.count() == 0
