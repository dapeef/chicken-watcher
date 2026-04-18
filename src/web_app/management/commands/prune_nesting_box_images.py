"""
Management command for cleaning up NestingBoxImage records.

Two modes, controlled by --all:

Default (``--all`` not set)
  "Prune" — delete images that are NOT within PROXIMITY_WINDOW of any
  NestingBoxPresencePeriod or Egg. Boring frames (no chicken, no egg)
  are removed; frames near activity are kept. This is safe to run in
  cron without any confirmation.

``--all``
  "Nuke" — delete ALL images, regardless of nearby activity. Requires
  explicit confirmation (interactive ``yes`` prompt or ``--yes`` flag)
  because it is irreversible.

Previously two separate commands (``prune_nesting_box_images`` and
``delete_nesting_box_images``) with an identical deletion loop. Merged
here to eliminate the duplication and keep a single entry point for
image-management operations.
"""

import logging
import sys
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from web_app.models import NestingBoxImage

logger = logging.getLogger(__name__)

# How close (in seconds) an image must be to a presence period or egg
# to be retained by the default prune mode.
PROXIMITY_WINDOW = timedelta(seconds=30)


class Command(BaseCommand):
    help = (
        "Delete NestingBoxImage records. "
        "Default: remove images with no nearby presence/egg activity. "
        "With --all: remove every image (requires --yes or confirmation)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            default=False,
            dest="delete_all",
            help=(
                "Delete ALL images regardless of nearby activity. "
                "Requires --yes or interactive confirmation."
            ),
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            default=False,
            help=(
                "Skip interactive confirmation. Required when --all is used "
                "in non-interactive contexts (cron, CI, piped stdin)."
            ),
        )

    def handle(self, *args, **options):
        delete_all: bool = options["delete_all"]
        yes: bool = options["yes"]

        if delete_all:
            self._handle_delete_all(yes=yes)
        else:
            self._handle_prune()

    def _handle_prune(self) -> None:
        """Delete images with no nearby activity. No confirmation needed."""
        images_to_delete = NestingBoxImage.objects.far_from_events(PROXIMITY_WINDOW)
        count = images_to_delete.count()

        if count == 0:
            logger.info("Nothing to prune.")
            return

        logger.info("Pruning %d NestingBoxImage records with no nearby presence or egg", count)
        deleted = _delete_queryset(images_to_delete, count)
        after = NestingBoxImage.objects.count()
        logger.info("Pruned %d NestingBoxImage records. %d remain.", deleted, after)

    def _handle_delete_all(self, yes: bool) -> None:
        """Delete every image. Requires confirmation."""
        total = NestingBoxImage.objects.count()

        if total == 0:
            logger.info("No NestingBoxImage records to delete.")
            return

        if not yes:
            _confirm_delete_all(total)

        logger.info("Deleting all %d NestingBoxImage records", total)
        deleted = _delete_queryset(NestingBoxImage.objects.all(), total)
        logger.info("Deleted %d NestingBoxImage(s).", deleted)


def _delete_queryset(qs, expected_count: int) -> int:
    """Delete every image in ``qs``, removing the file from disk before
    the DB row (safe order: if the process dies between the two, a stale
    file is better than a dangling DB row pointing at a missing file).

    Logs progress every 100 records. Returns the number deleted.
    """
    deleted = 0
    for image in qs.iterator():
        image.image.delete(save=False)
        image.delete()
        deleted += 1
        if deleted % 100 == 0:
            logger.info(
                "Deleted %d (of %d) NestingBoxImage records so far",
                deleted,
                expected_count,
            )
    return deleted


def _confirm_delete_all(total: int) -> None:
    """Interactively confirm deletion of all images. Raises
    ``CommandError`` if declined or running non-interactively."""
    if not sys.stdin.isatty():
        raise CommandError(
            f"Refusing to delete {total} NestingBoxImage(s) non-interactively. "
            "Pass --yes to confirm."
        )
    prompt = (
        f"\nThis will DELETE all {total} NestingBoxImage records and their "
        "underlying image files.\n"
        "Type 'yes' to proceed, anything else to abort: "
    )
    answer = input(prompt).strip().lower()
    if answer != "yes":
        raise CommandError("Aborted by user.")
