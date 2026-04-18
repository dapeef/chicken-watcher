import logging
import sys

from django.core.management.base import BaseCommand, CommandError

from web_app.models import NestingBoxImage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Delete all NestingBoxImage records and their associated image files. "
        "Requires interactive confirmation or --yes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            default=False,
            help="Skip interactive confirmation. Required in non-interactive contexts.",
        )

    def handle(self, *args, **options):
        """Deletes all NestingBoxImage records, including their image files on disk."""

        yes: bool = options["yes"]
        total = NestingBoxImage.objects.count()

        if total == 0:
            logger.info("No NestingBoxImage records to delete.")
            return

        if not yes:
            _confirm(total)

        logger.info(f"Deleting all {total} NestingBoxImage records")

        for count, image in enumerate(NestingBoxImage.objects.all(), start=1):
            image.image.delete(save=False)
            image.delete()
            if count % 100 == 0:
                logger.info(f"Deleted {count} (of {total}) NestingBoxImage records so far")

        logger.info(f"Deleted {total} NestingBoxImage(s).")


def _confirm(total: int) -> None:
    """Interactively confirm deletion of all nesting box images. Raises
    CommandError if the caller declines or the command is running
    non-interactively.
    """
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
