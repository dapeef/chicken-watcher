import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from web_app.models import NestingBoxImage, NestingBoxPresence

logger = logging.getLogger(__name__)

PRESENCE_WINDOW = timedelta(seconds=30)


class Command(BaseCommand):
    help = (
        "Delete NestingBoxImage records that are not within "
        f"{PRESENCE_WINDOW.seconds}s of any nesting box presence event."
    )

    def handle(self, *args, **options):
        before = NestingBoxImage.objects.count()
        delete_nesting_box_images_far_from_presence()
        after = NestingBoxImage.objects.count()
        deleted = before - after
        self.stdout.write(f"Deleted {deleted} NestingBoxImages. {after} remain.")


def get_images_to_delete():
    """
    Return a queryset of NestingBoxImages that are NOT within PRESENCE_WINDOW
    of any NestingBoxPresence event.
    """
    nearby_presence = NestingBoxPresence.objects.filter(
        present_at__gte=OuterRef("created_at") - PRESENCE_WINDOW,
        present_at__lte=OuterRef("created_at") + PRESENCE_WINDOW,
    )
    return NestingBoxImage.objects.filter(~Exists(nearby_presence))


def delete_nesting_box_images_far_from_presence():
    """
    Delete NestingBoxImage records (and their files on disk) that have no
    NestingBoxPresence event within PRESENCE_WINDOW of their created_at.
    """
    images_to_delete = get_images_to_delete()
    count = images_to_delete.count()

    logger.info(
        f"Pruning {count} NestingBoxImage records with no nearby presence event"
    )

    deleted = 0
    for image in images_to_delete.iterator():
        image.image.delete(save=False)
        image.delete()
        deleted += 1
        if deleted % 100 == 0:
            logger.info(f"Deleted {deleted} NestingBoxImage records so far")

    logger.info(f"Pruned {deleted} NestingBoxImage records")
