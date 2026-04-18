import csv
import datetime
from enum import StrEnum
from pathlib import Path
from random import randrange, randint, choice, random

from django.core.management.base import BaseCommand
from django.utils import timezone

from web_app.models import (
    Tag,
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
    SEED_TAGS = "seed_tags"  # Upsert tags from tags.csv


CHICKENS_CSV = Path(__file__).parent / "chickens.csv"
TAGS_CSV = Path(__file__).parent / "tags.csv"


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
        parser.add_argument(
            "--tags-csv-file",
            type=Path,
            default=None,
            help=f"Path to tags CSV file (used with --mode={SeedMode.SEED_TAGS}). Defaults to the bundled tags.csv.",
        )

    def handle(self, *args, **options):
        """Seed database based on mode"""

        mode: SeedMode = options["mode"]
        csv_file_raw = options["csv_file"]
        csv_file: Path | None = Path(csv_file_raw) if csv_file_raw is not None else None
        tags_csv_file_raw = options["tags_csv_file"]
        tags_csv_file: Path | None = (
            Path(tags_csv_file_raw) if tags_csv_file_raw is not None else None
        )

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
            case SeedMode.SEED_TAGS:
                seed_tags_from_csv(
                    tags_csv_file
                ) if tags_csv_file else seed_tags_from_csv()


def clear_data():
    """Deletes all the table data"""
    logger.info("Deleting all data")
    Chicken.objects.all().delete()
    Tag.objects.all().delete()
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

    # Chickens (with associated Tags)
    Chicken.objects.create(
        name="Islay",
        date_of_birth=datetime.date(2025, 2, 1),
        tag=Tag.objects.create(rfid_string="0D007FE20B", number=101),
    )
    Chicken.objects.create(
        name="Scramble",
        date_of_birth=datetime.date(2025, 8, 1),
        tag=Tag.objects.create(rfid_string="0D007FE20C", number=102),
    )
    Chicken.objects.create(
        name="Eigg",
        date_of_birth=datetime.date(2025, 9, 1),
        tag=Tag.objects.create(rfid_string="0D007FE20D", number=103),
    )
    Chicken.objects.create(
        name="Twiglet",
        date_of_birth=datetime.date(2025, 8, 5),
        tag=Tag.objects.create(rfid_string="0D007FE20E", number=104),
    )
    Chicken.objects.create(
        name="Hoppy",
        date_of_birth=datetime.date(2025, 9, 10),
        tag=Tag.objects.create(rfid_string="0D007FE20F", number=105),
    )
    Chicken.objects.create(
        name="Omelette",
        date_of_birth=datetime.date(2025, 1, 1),
        date_of_death=datetime.date(2025, 10, 1),
        tag=Tag.objects.create(rfid_string="0D007FFEFE", number=106),
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

                # Quality distribution: Hoppy occasionally lays messy eggs
                # (1 in 20 chance), any hen may lay edible-only eggs (1 in 10)
                if chicken.name == "Hoppy" and random() < 0.05:
                    quality = Egg.Quality.MESSY
                elif random() < 0.1:
                    quality = Egg.Quality.EDIBLE
                else:
                    quality = Egg.Quality.SALEABLE

                # Occasionally record an egg with an unknown chicken and/or box
                egg_chicken = None if random() < 0.05 else chicken
                egg_box = None if random() < 0.05 else nesting_box

                Egg.objects.create(
                    chicken=egg_chicken,
                    laid_at=egg_time,
                    nesting_box=egg_box,
                    quality=quality,
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
    """Upsert chickens from a CSV file (Name, DoB, Tag number).

    Matches on name: creates the chicken if it doesn't exist, updates it otherwise.
    The 'Tag number' column must reference an existing Tag.number in the database.
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
            tag_number = int(row["Tag number"].strip())

            try:
                tag = Tag.objects.get(number=tag_number)
            except Tag.DoesNotExist:
                logger.warning(
                    f"No Tag found with number {tag_number} for chicken '{name}' — skipping"
                )
                continue

            _, created = Chicken.objects.update_or_create(
                name=name,
                defaults={"date_of_birth": dob, "tag": tag},
            )

            if created:
                created_count += 1
                logger.info(f"Created chicken: {name}")
            else:
                updated_count += 1
                logger.info(f"Updated chicken: {name}")

    logger.info(f"Chickens seeded: {created_count} created, {updated_count} updated")


def seed_tags_from_csv(csv_path: Path = TAGS_CSV):
    """Upsert tags from a CSV file (Tag number, Tag ID).

    Matches on number: creates the tag if it doesn't exist, updates it otherwise.
    Does not delete any existing tags or touch any other data.
    """
    logger.info(f"Seeding tags from {csv_path}")
    created_count = 0
    updated_count = 0

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            number = int(row["Tag number"].strip())
            rfid_string = row["Tag ID"].strip()

            _, created = Tag.objects.update_or_create(
                number=number,
                defaults={"rfid_string": rfid_string},
            )

            if created:
                created_count += 1
                logger.info(f"Created tag: number={number}")
            else:
                updated_count += 1
                logger.info(f"Updated tag: number={number}")

    logger.info(f"Tags seeded: {created_count} created, {updated_count} updated")
