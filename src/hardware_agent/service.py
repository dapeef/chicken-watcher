import os
import time

from hardware_agent.rfid_reader import RFIDReader


import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

# Must be below `django.setup()` for the imports to work correctly
from web_app.models import NestingBoxPresence, NestingBox, Chicken # noqa: E402


def handle_tag_read(name: str, tag: str):
    print(f"{name} nesting box detected tag: {tag}")
    nesting_box = NestingBox.objects.get(name=name)
    chicken = Chicken.objects.get(tag_string=tag)

    NestingBoxPresence.objects.create(nesting_box=nesting_box, chicken=chicken)

def main():
    rfid_reader = RFIDReader("left", os.environ.get("RFID_SERIAL_PORT_LEFT"))

    rfid_reader.connect()

    rfid_reader.start_reading(handle_tag_read)

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
