import os
import pathlib
import signal
from datetime import datetime

import cv2
from django.core.files.base import ContentFile
from django.db import transaction
from gpiozero.pins.lgpio import LGPIOFactory

from hardware_agent.beam_break_sensor import BeamSensor
from hardware_agent.camera import USBCamera
from hardware_agent.rfid_reader import RFIDReader
from web_app.models import NestingBoxPresence, NestingBox, Chicken, NestingBoxImage, Egg


def handle_tag_read(name: str, tag: str):
    print(f"[{name}] Nesting box detected tag: {tag}")
    try:
        nesting_box = NestingBox.objects.get(name=name)
        chicken = Chicken.objects.get(tag_string=tag)

        NestingBoxPresence.objects.create(nesting_box=nesting_box, chicken=chicken)

        print(f"[{name}] Chicken {chicken.name} (tag: {tag}) added to nesting box")

    except Chicken.DoesNotExist:
        print(f"Error: No matching chicken found matching tag: {tag}")


def save_frame_to_file(cam_name, frame):
    frame_dir = pathlib.Path("frames")
    frame_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    file_name = frame_dir / f"{cam_name}_{ts}.jpg"
    cv2.imwrite(str(file_name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])


def save_frame_to_db(cam_name: str, frame):
    """
    frame: numpy.ndarray returned by cv2.VideoCapture.read()
    """
    # Django needs to save a file, not just the pixels

    # 1) encode ndarray → JPEG bytes
    success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not success:
        raise RuntimeError("Could not encode frame to JPEG")

    # 2) build a unique filename (cam + timestamp or UUID)
    ts = datetime.now().strftime("%Y%m%dT%H%M%S%f")[:-3]
    filename = f"{cam_name}_{ts}.jpg"

    # 3) wrap in ContentFile and give it the filename
    django_file = ContentFile(buffer.tobytes(), name=filename)

    # 4) create the DB row
    NestingBoxImage.objects.create(image=django_file)

    print(f"{cam_name} frame saved to db as {filename}")


@transaction.atomic
def handle_beam_break(name: str) -> None:
    print(f"[{name}] Beam break detected")

    nesting_box = NestingBox.objects.get(name=name)

    # Find the most recent presence for that box
    presence = (
        NestingBoxPresence.objects.filter(nesting_box=nesting_box)
        .select_related("chicken")
        .order_by("present_at")
        .last()
    )
    if presence is None:
        raise ValueError(f"No NestingBoxPresence found for box '{name}'")

    Egg.objects.create(nesting_box=nesting_box, chicken=presence.chicken)


def run_agent():
    rfid_reader = RFIDReader("left", os.environ.get("RFID_PORT_BY_ID_LEFT"))
    rfid_reader.connect()
    rfid_reader.start_reading(handle_tag_read)

    rfid_reader = RFIDReader("right", os.environ.get("RFID_PORT_BY_ID_RIGHT"))
    rfid_reader.connect()
    rfid_reader.start_reading(handle_tag_read)

    camera = USBCamera("cam", device=os.environ.get("CAMERA_DEVICE_BY_ID"), fps=1)
    camera.connect()
    camera.start_capturing(save_frame_to_db)

    pin_factory = LGPIOFactory(chip=0)

    beam_break_left = BeamSensor("left", int(os.environ.get("BEAM_BREAK_GPIO_LEFT")), pin_factory=pin_factory)
    beam_break_left.connect()
    beam_break_left.start_reading(handle_beam_break)

    beam_break_right = BeamSensor("right", int(os.environ.get("BEAM_BREAK_GPIO_RIGHT")), pin_factory=pin_factory)
    beam_break_right.connect()
    beam_break_right.start_reading(handle_beam_break)

    print("All sensors initialised")

    signal.pause()


if __name__ == "__main__":
    run_agent()
