import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef

from web_app.models import Egg, NestingBoxImage, NestingBoxPresencePeriod

logger = logging.getLogger(__name__)

WINDOW = timedelta(seconds=30)


class Command(BaseCommand):
    help = (
        "Delete NestingBoxImage records that are not within "
        f"{WINDOW.seconds}s of any nesting box presence period or egg."
    )

    def handle(self, *args, **options):
        """
        Delete NestingBoxImage records (and their files on disk) that have no
        NestingBoxPresencePeriod or Egg within WINDOW of their created_at.
        """

        logger.info("Collecting NestingBoxImage records with no nearby presence or egg")

        images_to_delete = get_images_to_delete()
        count = images_to_delete.count()

        logger.info(
            f"Pruning {count} NestingBoxImage records with no nearby presence or egg"
        )

        deleted = 0
        for image in images_to_delete.iterator():
            image.image.delete(save=False)
            image.delete()
            deleted += 1
            if deleted % 100 == 0:
                logger.info(
                    f"Deleted {deleted} (of {count}) NestingBoxImage records so far"
                )

        after = NestingBoxImage.objects.count()

        logger.info(f"Pruned {deleted} NestingBoxImage records. {after} remain.")


def get_images_to_delete():
    """
    Return a queryset of NestingBoxImages that are NOT within WINDOW of any
    NestingBoxPresencePeriod or Egg.
    """
    nearby_presence = NestingBoxPresencePeriod.objects.filter(
        started_at__lte=OuterRef("created_at") + WINDOW,
        ended_at__gte=OuterRef("created_at") - WINDOW,
    )
    nearby_egg = Egg.objects.filter(
        laid_at__gte=OuterRef("created_at") - WINDOW,
        laid_at__lte=OuterRef("created_at") + WINDOW,
    )
    return NestingBoxImage.objects.filter(
        ~Exists(nearby_presence) & ~Exists(nearby_egg)
    )
