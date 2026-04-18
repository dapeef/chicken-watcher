"""
Upsert chickens from a CSV file.

Thin wrapper around ``seed --mode=seed_chickens`` for discoverability.
Allows callers to run ``manage.py import_chickens`` without needing to
know about the seed command's mode flag.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Upsert chickens from a CSV file (wraps seed --mode=seed_chickens)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-file",
            default=None,
            help="Path to the CSV file. Defaults to the bundled chickens.csv.",
        )

    def handle(self, *args, **options):
        call_command(
            "seed",
            mode="seed_chickens",
            csv_file=options["csv_file"],
        )
