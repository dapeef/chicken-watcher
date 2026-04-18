import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from web_app.models import NestingBoxImage
from test.web_app.factories import NestingBoxImageFactory


@pytest.mark.django_db
def test_delete_nesting_box_images_removes_all_records():
    NestingBoxImageFactory.create_batch(3)
    assert NestingBoxImage.objects.count() == 3

    call_command("delete_nesting_box_images", yes=True)

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_delete_nesting_box_images_deletes_image_files(mocker):
    images = NestingBoxImageFactory.create_batch(2)
    mock_delete = mocker.patch("django.db.models.fields.files.FieldFile.delete")

    call_command("delete_nesting_box_images", yes=True)

    assert mock_delete.call_count == len(images)
    mock_delete.assert_called_with(False)


@pytest.mark.django_db
def test_delete_nesting_box_images_when_none_exist():
    assert NestingBoxImage.objects.count() == 0

    # No guard invoked when there's nothing to delete.
    call_command("delete_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


# ---------------------------------------------------------------------------
# Destructive-guard tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_delete_refuses_without_yes_when_non_interactive(mocker):
    """Non-interactive runs (stdin not a TTY) must pass --yes explicitly.
    This simulates the command running under cron / CI / piped stdin."""
    NestingBoxImageFactory.create_batch(2)
    mocker.patch("sys.stdin.isatty", return_value=False)

    with pytest.raises(CommandError, match="--yes"):
        call_command("delete_nesting_box_images")

    # Data must be untouched
    assert NestingBoxImage.objects.count() == 2


@pytest.mark.django_db
def test_delete_prompts_interactively_and_proceeds_on_yes(mocker):
    """Interactive runs with 'yes' reply delete the records."""
    NestingBoxImageFactory.create_batch(2)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("builtins.input", return_value="yes")

    call_command("delete_nesting_box_images")

    assert NestingBoxImage.objects.count() == 0


@pytest.mark.django_db
def test_delete_prompts_interactively_and_aborts_on_other_input(mocker):
    """Interactive runs with anything other than 'yes' abort cleanly."""
    NestingBoxImageFactory.create_batch(2)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mocker.patch("builtins.input", return_value="no")

    with pytest.raises(CommandError, match="Aborted"):
        call_command("delete_nesting_box_images")

    # Data must be untouched
    assert NestingBoxImage.objects.count() == 2


@pytest.mark.django_db
def test_delete_yes_flag_bypasses_prompt(mocker):
    """--yes skips the prompt entirely, even in an interactive terminal."""
    NestingBoxImageFactory.create_batch(2)
    mocker.patch("sys.stdin.isatty", return_value=True)
    mock_input = mocker.patch("builtins.input")

    call_command("delete_nesting_box_images", yes=True)

    assert mock_input.call_count == 0
    assert NestingBoxImage.objects.count() == 0
