import pathlib
from datetime import datetime
import time

import cv2
from django.core.files.base import ContentFile


from web_app.models import NestingBoxPresence, NestingBox, Chicken, NestingBoxImage


def handle_tag_read(name: str, tag: str):
    print(f"{name} nesting box detected tag: {tag}")
    try:
        nesting_box = NestingBox.objects.get(name=name)
        chicken = Chicken.objects.get(tag_string=tag)

        NestingBoxPresence.objects.create(nesting_box=nesting_box, chicken=chicken)

    except Chicken.DoesNotExist:
        print("Error: Tag not found")


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

    print(f"{cam_name} frame saved as {filename}")


def run_agent():
    # rfid_reader = RFIDReader("left", os.environ.get("RFID_SERIAL_PORT_LEFT"))
    # rfid_reader.connect()
    # rfid_reader.start_reading(handle_tag_read)
    #
    # camera = USBCamera("cam", device_index=0, fps=1)
    # camera.connect()
    # camera.start_capturing(save_frame)

    # # Just to test the db connection
    # create_some_eggs()

    # To test the image creation
    dummy_image = cv2.imread("./src/dummy_image.JPG")
    save_frame_to_db("dummy_image", dummy_image)

    handle_tag_read("arst", "arst")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    run_agent()
