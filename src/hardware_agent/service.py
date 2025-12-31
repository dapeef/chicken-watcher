import pathlib
from datetime import datetime
import os
import time

import cv2

from hardware_agent.camera import USBCamera
from hardware_agent.rfid_reader import RFIDReader

from web_app.models import NestingBoxPresence, NestingBox, Chicken  # noqa: E402


def handle_tag_read(name: str, tag: str):
    print(f"{name} nesting box detected tag: {tag}")
    nesting_box = NestingBox.objects.get(name=name)
    chicken = Chicken.objects.get(tag_string=tag)

    NestingBoxPresence.objects.create(nesting_box=nesting_box, chicken=chicken)


frame_dir = pathlib.Path("frames")
frame_dir.mkdir(exist_ok=True)


def save_frame(cam_name, frame):
    # timestamp-based file name, e.g. Lobby-Cam_2025-01-07T14:23:15.123.jpg
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    file_name = frame_dir / f"{cam_name}_{ts}.jpg"
    cv2.imwrite(str(file_name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])


def run_agent():
    rfid_reader = RFIDReader("left", os.environ.get("RFID_SERIAL_PORT_LEFT"))
    rfid_reader.connect()
    rfid_reader.start_reading(handle_tag_read)

    camera = USBCamera("cam", device_index=0, fps=1)
    camera.connect()
    camera.start_capturing(save_frame)

    # # Just to test the db connection
    # create_some_eggs()

    while True:
        time.sleep(1)


if __name__ == "__main__":
    run_agent()
