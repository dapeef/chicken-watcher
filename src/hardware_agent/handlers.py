import pathlib
from datetime import datetime, timedelta

import cv2
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from web_app.models import (
    NestingBoxPresence,
    NestingBox,
    Chicken,
    NestingBoxImage,
    Egg,
    HardwareSensor,
    NestingBoxPresencePeriod,
)


def report_status(full_name: str, connected: bool, message: str = ""):
    try:
        HardwareSensor.objects.update_or_create(
            name=full_name,
            defaults={
                "is_connected": connected,
                "status_message": message,
                "last_seen_at": timezone.now(),
            },
        )
    except Exception as e:
        print(f"Error reporting status for {full_name}: {e}")


def report_event(full_name: str):
    try:
        HardwareSensor.objects.filter(name=full_name).update(
            last_event_at=timezone.now(), is_connected=True
        )
    except Exception as e:
        print(f"Error reporting event for {full_name}: {e}")


NESTING_BOX_PRESENCE_TIMEOUT = 60


@transaction.atomic
def handle_tag_read(name: str, tag: str):
    report_event(f"rfid_{name}")
    print(f"[{name}] Nesting box detected tag: {tag}")
    try:
        nesting_box = NestingBox.objects.get(name=name)
        chicken = Chicken.objects.get(tag_string=tag)

        now = timezone.now()

        # Look for an existing period for this chicken in this box that ended recently
        recent_period = (
            NestingBoxPresencePeriod.objects.filter(
                chicken=chicken,
                nesting_box=nesting_box,
                ended_at__gte=now - timedelta(seconds=NESTING_BOX_PRESENCE_TIMEOUT),
            )
            .order_by("ended_at")
            .last()
        )

        if recent_period:
            # Check if there is a more recent period in a different box
            if (
                NestingBoxPresencePeriod.objects.filter(
                    chicken=chicken, ended_at__gt=recent_period.ended_at
                )
                .exclude(nesting_box=nesting_box)
                .exists()
            ):
                recent_period = None

        if recent_period:
            recent_period.ended_at = now
            recent_period.save()
            period = recent_period
        else:
            period = NestingBoxPresencePeriod.objects.create(
                chicken=chicken, nesting_box=nesting_box, started_at=now, ended_at=now
            )

        NestingBoxPresence.objects.create(
            nesting_box=nesting_box,
            chicken=chicken,
            present_at=now,
            presence_period=period,
        )

        print(
            f"[{name}] Chicken {chicken.name} (tag: {tag}) added to nesting box. Period ID: {period.id}"
        )

    except Chicken.DoesNotExist:
        print(f"Error: No matching chicken found matching tag: {tag}")
    except NestingBox.DoesNotExist:
        print(f"Error: No matching nesting box found matching name: {name}")


def save_frame_to_file(cam_name, frame):
    frame_dir = pathlib.Path("frames")
    frame_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    file_name = frame_dir / f"{cam_name}_{ts}.jpg"
    cv2.imwrite(str(file_name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])


def handle_camera_frame(name: str, frame):
    report_event(f"camera_{name}")
    save_frame_to_db(name, frame)


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
    report_event(f"beam_{name}")
    print(f"[{name}] Beam break detected")

    try:
        nesting_box = NestingBox.objects.get(name=name)

        # Find the most recent presence for that box
        presence = (
            NestingBoxPresence.objects.filter(nesting_box=nesting_box)
            .select_related("chicken")
            .order_by("present_at")
            .last()
        )
        if presence is None:
            print(f"Warning: No NestingBoxPresence found for box '{name}'")
            return

        Egg.objects.create(nesting_box=nesting_box, chicken=presence.chicken)
    except NestingBox.DoesNotExist:
        print(f"Error: No matching nesting box found matching name: {name}")
    except Exception as e:
        print(f"Error handling beam break: {e}")
