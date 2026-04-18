"""
Ensure the standard nesting boxes exist.

Thin wrapper around ``seed --mode=seed_nesting_boxes`` for discoverability.
Idempotent — safe to run on every deployment.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Ensure the standard nesting boxes exist (idempotent)."

    def handle(self, *args, **options):
        call_command("seed", mode="seed_nesting_boxes")
