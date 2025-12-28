from django.core.management.base import BaseCommand
from hardware_agent.service import run_agent   # refactor main() to run_agent()

class Command(BaseCommand):
    help = "Start RFID hardware agent"

    def handle(self, *args, **opts):
        run_agent()