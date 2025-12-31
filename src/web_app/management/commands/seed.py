import datetime
from random import randrange, randint, choice, random

from django.core.management.base import BaseCommand
from django.utils import timezone

from web_app.models import Chicken, NestingBox, Egg, NestingBoxPresence

import logging

logger = logging.getLogger(__name__)

# uv run manage.py seed --mode=refresh

""" Clear all data and creates addresses """
MODE_REFRESH = "refresh"

""" Clear all data and do not create any object """
MODE_CLEAR = "clear"


class Command(BaseCommand):
    help = "seed database for testing and development."

    def add_arguments(self, parser):
        parser.add_argument("--mode", type=str, help="Mode")

    def handle(self, *args, **options):
        self.stdout.write("Seeding data...")
        run_seed(options["mode"])
        self.stdout.write("Data seeding complete.")


def clear_data():
    """Deletes all the table data"""
    logger.info("Deleting all data")
    Chicken.objects.all().delete()
    NestingBox.objects.all().delete()
    Egg.objects.all().delete()
    NestingBoxPresence.objects.all().delete()


TZ = timezone.get_current_timezone()


def populate_data():
    """Populates Chicken and NestingBox"""

    def random_date(
        start: datetime.datetime, end: datetime.datetime
    ) -> datetime.datetime:
        """
        This function will return a random datetime between two datetime objects.
        """
        delta = end - start
        int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
        random_second = randrange(int_delta)
        return start + datetime.timedelta(seconds=random_second)

    logger.info("Populating Chicken and NestingBox")

    # Chickens
    Chicken.objects.create(
        name="Isla", date_of_birth=datetime.date(2025, 2, 1), tag_string="0D007FE20B"
    )
    Chicken.objects.create(
        name="Scramble",
        date_of_birth=datetime.date(2025, 8, 1),
        tag_string="0D007FE20C",
    )
    Chicken.objects.create(
        name="Eigg", date_of_birth=datetime.date(2025, 9, 1), tag_string="0D007FE20D"
    )
    Chicken.objects.create(
        name="Twiglet", date_of_birth=datetime.date(2025, 8, 5), tag_string="0D007FE20E"
    )
    Chicken.objects.create(
        name="Hoppy", date_of_birth=datetime.date(2025, 9, 10), tag_string="0D007FE20F"
    )
    Chicken.objects.create(
        name="Omelette",
        date_of_birth=datetime.date(2025, 1, 1),
        date_of_death=datetime.date(2025, 10, 1),
        tag_string="0D007FFEFE",
    )

    # Nesting boxes
    NestingBox.objects.create(name="left")
    NestingBox.objects.create(name="right")

    # Eggs and nesting box presences
    logger.info("Populating Egg and NestingBoxPresence")
    for chicken in Chicken.objects.all():
        logger.info(f"For chicken: {chicken.name}")

        last_day = chicken.date_of_death or datetime.date.today()
        first_day = chicken.date_of_birth

        delta = last_day - first_day

        for i in range(delta.days + 1):
            if random() < 0.8:  # Chicken lays an egg 9 in 10 days
                day = first_day + datetime.timedelta(days=i)

                day_start = datetime.datetime(
                    year=day.year, month=day.month, day=day.day, tzinfo=TZ
                )

                earliest_egg = day_start + datetime.timedelta(hours=6)
                latest_egg = min(
                    day_start + datetime.timedelta(hours=20), timezone.localtime()
                )
                start_time = random_date(earliest_egg, latest_egg)

                seconds_in_box = randint(10, 5 * 60)  # Between 10 secs and 5 mins

                nesting_box = choice(list(NestingBox.objects.all()))

                for delta_secs in range(seconds_in_box):
                    NestingBoxPresence.objects.create(
                        nesting_box=nesting_box,
                        present_at=start_time + datetime.timedelta(seconds=delta_secs),
                        chicken=chicken,
                    )

                egg_time = start_time + datetime.timedelta(
                    seconds=seconds_in_box - 5
                )  # Egg laid 5s before departure

                Egg.objects.create(
                    chicken=chicken, laid_at=egg_time, nesting_box=nesting_box
                )

    logger.info("DB populated")


def run_seed(mode):
    """Seed database based on mode

    :param mode: refresh / clear
    :return:
    """
    # Clear data from tables
    clear_data()
    if mode == MODE_CLEAR:
        return

    populate_data()
