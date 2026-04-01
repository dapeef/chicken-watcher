import logging

from django.core.management.base import BaseCommand

from web_app.models import NestingBoxImage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete all NestingBoxImage records and their associated image files."

    def handle(self, *args, **options):
        """Deletes all NestingBoxImage records, including their image files on disk."""

        total = NestingBoxImage.objects.count()

        logger.info(f"Deleting all {total} NestingBoxImage records")

        for count, image in enumerate(NestingBoxImage.objects.all(), start=1):
            image.image.delete(save=False)
            image.delete()
            if count % 100 == 0:
                logger.info(
                    f"Deleted {count} (of {total}) NestingBoxImage records so far"
                )

        logger.info(f"Deleted {total} NestingBoxImage(s).")
