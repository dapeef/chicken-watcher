import datetime

from django.core.management.base import BaseCommand

from web_app.models import Chicken, NestingBox, Egg, NestingBoxVisit

import logging
logger = logging.getLogger(__name__)


# uv run manage.py seed --mode=refresh

""" Clear all data and creates addresses """
MODE_REFRESH = 'refresh'

""" Clear all data and do not create any object """
MODE_CLEAR = 'clear'

class Command(BaseCommand):
    help = "seed database for testing and development."

    def add_arguments(self, parser):
        parser.add_argument('--mode', type=str, help="Mode")

    def handle(self, *args, **options):
        self.stdout.write('seeding data...')
        run_seed(options['mode'])
        self.stdout.write('done.')


def clear_data():
    """Deletes all the table data"""
    logger.info("Deleting all data")
    Chicken.objects.all().delete()
    NestingBox.objects.all().delete()
    Egg.objects.all().delete()
    NestingBoxVisit.objects.all().delete()


def populate_data():
    """Populates Chicken and NestingBox"""
    logger.info("Populating Chicken and NestingBox")

    Chicken.objects.create(name='Isla', date_of_birth=datetime.date(2020, 1, 1), tag_string="abc")
    Chicken.objects.create(name='Omelette', date_of_birth=datetime.date(2020, 1, 1), date_of_death=datetime.date(2025, 1, 1), tag_string="abc")

    NestingBox.objects.create(name='left')
    NestingBox.objects.create(name='right')

    logger.info("DB populated")

def run_seed(mode):
    """ Seed database based on mode

    :param mode: refresh / clear
    :return:
    """
    # Clear data from tables
    clear_data()
    if mode == MODE_CLEAR:
        return

    populate_data()
