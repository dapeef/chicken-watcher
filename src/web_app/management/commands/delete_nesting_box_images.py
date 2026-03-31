import logging

from django.core.management.base import BaseCommand

from web_app.models import NestingBoxImage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete all NestingBoxImage records and their associated image files."

    def handle(self, *args, **options):
        count = NestingBoxImage.objects.count()
        delete_all_nesting_box_images()
        self.stdout.write(f"Deleted {count} NestingBoxImage(s).")


def delete_all_nesting_box_images():
    """Deletes all NestingBoxImage records, including their image files on disk."""
    logger.info(f"Deleting all {NestingBoxImage.objects.count()} NestingBoxImage records")
    for image in NestingBoxImage.objects.all():
        image.image.delete(save=False)
        image.delete()
    logger.info("All NestingBoxImage records deleted")
