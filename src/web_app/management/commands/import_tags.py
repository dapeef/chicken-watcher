"""
Upsert tags from a CSV file.

Thin wrapper around ``seed --mode=seed_tags`` for discoverability.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Upsert RFID tags from a CSV file (wraps seed --mode=seed_tags)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-file",
            default=None,
            help="Path to the CSV file. Defaults to the bundled tags.csv.",
        )

    def handle(self, *args, **options):
        call_command(
            "seed",
            mode="seed_tags",
            tags_csv_file=options["csv_file"],
        )
