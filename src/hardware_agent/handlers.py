import logging
import pathlib
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

import cv2
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from web_app.models import (
    NestingBoxPresence,
    NestingBox,
    Chicken,
    Tag,
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
        logger.error("Error reporting status for %s: %s", full_name, e)


def report_event(full_name: str):
    try:
        HardwareSensor.objects.filter(name=full_name).update(
            last_event_at=timezone.now(), is_connected=True
        )
    except Exception as e:
        logger.error("Error reporting event for %s: %s", full_name, e)


NESTING_BOX_PRESENCE_TIMEOUT = 60


def _nesting_box_name_for_sensor(sensor_name: str) -> str:
    """Derive the nesting box name from a sensor name.

    Sensors may be named with an alphabetic suffix to distinguish multiple
    sensors in the same box (e.g. ``"left_a"``, ``"left_b"`` → ``"left"``).
    If the name has no such suffix the name itself is used as-is (e.g.
    ``"left"`` → ``"left"``).
    """
    # Strip a trailing ``_<single-letter>`` suffix (case-insensitive).
    match = re.fullmatch(r"(.+)_([a-zA-Z])$", sensor_name)
    if match:
        return match.group(1)
    return sensor_name


@transaction.atomic
def handle_tag_read(name: str, tag: str):
    """Handle an RFID tag read event from a sensor named *name*.

    *name* is the sensor identifier (e.g. ``"left"``, ``"left_a"``,
    ``"left_b"``).  The corresponding nesting box is looked up by deriving
    the box name from *name* via :func:`_nesting_box_name_for_sensor`.
    The original sensor name is stored on the presence records so that
    individual sensors can be distinguished on the timeline.
    """
    report_event(f"rfid_{name}")
    logger.info("[%s] Nesting box detected tag: %s", name, tag)
    box_name = _nesting_box_name_for_sensor(name)
    try:
        nesting_box = NestingBox.objects.get(name=box_name)
        tag_obj = Tag.objects.get(rfid_string=tag)
        chicken = Chicken.objects.get(tag=tag_obj, date_of_death__isnull=True)

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
                chicken=chicken,
                nesting_box=nesting_box,
                started_at=now,
                ended_at=now,
            )

        NestingBoxPresence.objects.create(
            nesting_box=nesting_box,
            chicken=chicken,
            present_at=now,
            presence_period=period,
            sensor_id=name,
        )

        logger.info(
            "[%s] Chicken %s (tag: %s) added to nesting box. Period ID: %s",
            name,
            chicken.name,
            tag,
            period.id,
        )

    except Tag.DoesNotExist:
        logger.error("No tag found matching rfid string: %s", tag)
    except Chicken.DoesNotExist:
        logger.error("No live chicken found assigned to tag: %s", tag)
    except NestingBox.DoesNotExist:
        logger.error("No matching nesting box found matching name: %s", box_name)


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

    logger.debug("%s frame saved to db as %s", cam_name, filename)


@transaction.atomic
def handle_beam_break(name: str) -> None:
    report_event(f"beam_{name}")
    logger.info("[%s] Beam break detected", name)

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
            logger.warning("No NestingBoxPresence found for box '%s'", name)
            return

        Egg.objects.create(nesting_box=nesting_box, chicken=presence.chicken)
    except NestingBox.DoesNotExist:
        logger.error("No matching nesting box found matching name: %s", name)
    except Exception as e:
        logger.error("Error handling beam break: %s", e)
