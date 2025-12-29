import os
import time

from hardware_agent.create_egg_service import create_some_eggs
from hardware_agent.rfid_reader import RFIDReader

from web_app.models import NestingBoxPresence, NestingBox, Chicken  # noqa: E402


def handle_tag_read(name: str, tag: str):
    print(f"{name} nesting box detected tag: {tag}")
    nesting_box = NestingBox.objects.get(name=name)
    chicken = Chicken.objects.get(tag_string=tag)

    NestingBoxPresence.objects.create(nesting_box=nesting_box, chicken=chicken)


def run_agent():
    rfid_reader = RFIDReader("left", os.environ.get("RFID_SERIAL_PORT_LEFT"))

    rfid_reader.connect()

    rfid_reader.start_reading(handle_tag_read)

    # Just to test the db connection
    create_some_eggs()

    while True:
        time.sleep(1)


if __name__ == "__main__":
    run_agent()
