import csv
import datetime
from enum import StrEnum
from pathlib import Path
from random import randrange, randint, choice, random

from django.core.management.base import BaseCommand
from django.utils import timezone

from web_app.models import (
    Chicken,
    NestingBox,
    Egg,
    NestingBoxPresencePeriod,
)

import logging

logger = logging.getLogger(__name__)

# uv run manage.py seed --mode=refresh


class SeedMode(StrEnum):
    SPAWN_TEST_DATA = "spawn_test_data"  # Clear all data and populate with fake test data (non-prod only)
    CLEAR = "clear"  # Clear all data and do not create any objects
    SEED_CHICKENS = "seed_chickens"  # Upsert chickens from chickens.csv
    SEED_NESTING_BOXES = "seed_nesting_boxes"  # Ensure the standard nesting boxes exist


CHICKENS_CSV = Path(__file__).parent / "chickens.csv"


class Command(BaseCommand):
    help = "seed database for testing and development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            type=SeedMode,
            choices=list(SeedMode),
            required=True,
            help="Seed mode.",
        )
        parser.add_argument(
            "--csv-file",
            type=Path,
            default=None,
            help=f"Path to chickens CSV file (used with --mode={SeedMode.SEED_CHICKENS}). Defaults to the bundled chickens.csv.",
        )

    def handle(self, *args, **options):
        """Seed database based on mode"""

        mode: SeedMode = options["mode"]
        csv_file_raw = options["csv_file"]
        csv_file: Path | None = Path(csv_file_raw) if csv_file_raw is not None else None

        match mode:
            case SeedMode.SPAWN_TEST_DATA:
                clear_data()
                populate_data()
            case SeedMode.CLEAR:
                clear_data()
            case SeedMode.SEED_CHICKENS:
                seed_chickens_from_csv(
                    csv_file
                ) if csv_file else seed_chickens_from_csv()
            case SeedMode.SEED_NESTING_BOXES:
                seed_nesting_boxes()


def clear_data():
    """Deletes all the table data"""
    logger.info("Deleting all data")
    Chicken.objects.all().delete()
    NestingBox.objects.all().delete()
    Egg.objects.all().delete()
    NestingBoxPresencePeriod.objects.all().delete()


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
    seed_nesting_boxes()

    # Eggs and nesting box presence periods
    logger.info("Populating Egg and NestingBoxPresencePeriod")
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

                NestingBoxPresencePeriod.objects.create(
                    chicken=chicken,
                    nesting_box=nesting_box,
                    started_at=start_time,
                    ended_at=start_time + datetime.timedelta(seconds=seconds_in_box),
                )

                egg_time = start_time + datetime.timedelta(
                    seconds=seconds_in_box - 5
                )  # Egg laid 5s before departure

                Egg.objects.create(
                    chicken=chicken, laid_at=egg_time, nesting_box=nesting_box
                )

    logger.info("DB populated")


def seed_nesting_boxes():
    """Ensure the standard nesting boxes (left, right) exist.

    Uses get_or_create so it is safe to run against a database that already
    has the boxes — it will not create duplicates.
    """
    for name in ("left", "right"):
        _, created = NestingBox.objects.get_or_create(name=name)
        if created:
            logger.info(f"Created nesting box: {name}")
        else:
            logger.info(f"Nesting box already exists: {name}")


def seed_chickens_from_csv(csv_path: Path = CHICKENS_CSV):
    """Upsert chickens from a CSV file (Name, DoB, Tag ID).

    Matches on name: creates the chicken if it doesn't exist, updates it otherwise.
    Does not delete any existing chickens or touch any other data.
    """
    logger.info(f"Seeding chickens from {csv_path}")
    created_count = 0
    updated_count = 0

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["Name"].strip()
            dob = datetime.date.fromisoformat(row["DoB"].strip())
            tag_string = row["Tag ID"].strip()

            _, created = Chicken.objects.update_or_create(
                name=name,
                defaults={"date_of_birth": dob, "tag_string": tag_string},
            )

            if created:
                created_count += 1
                logger.info(f"Created chicken: {name}")
            else:
                updated_count += 1
                logger.info(f"Updated chicken: {name}")

    logger.info(f"Chickens seeded: {created_count} created, {updated_count} updated")
