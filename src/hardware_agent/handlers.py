import logging
import pathlib
import re
from datetime import datetime, timedelta

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

logger = logging.getLogger(__name__)


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

    Sensors are named with a ``_<digit>`` suffix to distinguish multiple
    sensors in the same box (e.g. ``"left_1"``, ``"left_2"`` → ``"left"``).
    If the name has no such suffix the name itself is used as-is (e.g.
    ``"left"`` → ``"left"``).
    """
    # Strip a trailing ``_<digits>`` suffix.
    match = re.fullmatch(r"(.+)_(\d+)$", sensor_name)
    if match:
        return match.group(1)
    return sensor_name


def handle_tag_read(name: str, tag: str):
    """Handle an RFID tag read event from a sensor named *name*.

    *name* is the sensor identifier (e.g. ``"left"``, ``"left_a"``,
    ``"left_b"``).  The corresponding nesting box is looked up by deriving
    the box name from *name* via :func:`_nesting_box_name_for_sensor`.
    The original sensor name is stored on the presence records so that
    individual sensors can be distinguished on the timeline.

    Each nesting box has up to four RFID readers. Without coordination,
    concurrent reads of the same tag from different readers in the same box
    race each other: both transactions see "no recent period exists" and
    each INSERTs a fresh one, producing duplicates. We serialise on the
    ``Chicken`` row via ``select_for_update`` so only one handler at a time
    can extend-or-create a period for any given chicken.
    """
    # These two sit outside the transaction so an in-flight event is still
    # reported even if the per-read transaction rolls back.
    report_event(f"rfid_{name}")
    logger.info("[%s] Nesting box detected tag: %s", name, tag)

    box_name = _nesting_box_name_for_sensor(name)
    try:
        _record_tag_read(name=name, tag=tag, box_name=box_name)
    except Tag.DoesNotExist:
        logger.error("No tag found matching rfid string: %s", tag)
    except Chicken.DoesNotExist:
        logger.error("No live chicken found assigned to tag: %s", tag)
    except NestingBox.DoesNotExist:
        logger.error("No matching nesting box found matching name: %s", box_name)


@transaction.atomic
def _record_tag_read(*, name: str, tag: str, box_name: str) -> None:
    """Resolve the box/tag/chicken and record the presence. Raises the
    standard DoesNotExist exceptions if any lookup fails; they're caught
    and logged by the caller.

    The ``Chicken`` row is locked for update (``select_for_update``) at the
    start of the transaction. This serialises all handlers operating on
    the same chicken, so the period-extend-or-create logic executes
    without races. On SQLite ``select_for_update`` is a no-op but SQLite
    serialises all writes anyway, so correctness is preserved.
    """
    nesting_box = NestingBox.objects.get(name=box_name)
    tag_obj = Tag.objects.get(rfid_string=tag)

    # Lock the chicken row. Any concurrent handler reading the same chicken
    # will block here until we commit, guaranteeing a consistent view of
    # that chicken's presence periods for the duration of this transaction.
    chicken = Chicken.objects.select_for_update().get(
        tag=tag_obj, date_of_death__isnull=True
    )

    now = timezone.now()

    # Find the most recent period for this chicken+box, then check whether
    # a later period in a different box makes it stale. With the chicken
    # lock held, no concurrent transaction can insert between these two
    # queries.
    recent_period = _find_extensible_period(chicken, nesting_box, now)

    if recent_period is not None:
        recent_period.ended_at = now
        recent_period.save(update_fields=["ended_at"])
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


def _find_extensible_period(chicken, nesting_box, now):
    """Return a :class:`NestingBoxPresencePeriod` for ``chicken``+``nesting_box``
    that can be extended to ``now``, or ``None`` if a new period should
    be created.

    A period is extensible when:

    * it ended within :data:`NESTING_BOX_PRESENCE_TIMEOUT` seconds of ``now``, and
    * no later period exists for the same chicken in a different box
      (which would indicate the chicken left this box after that period
      ended).

    Must be called inside a transaction with the chicken row locked.
    """
    recent_period = (
        NestingBoxPresencePeriod.objects.filter(
            chicken=chicken,
            nesting_box=nesting_box,
            ended_at__gte=now - timedelta(seconds=NESTING_BOX_PRESENCE_TIMEOUT),
        )
        .order_by("ended_at")
        .last()
    )

    if recent_period is None:
        return None

    seen_elsewhere_since = (
        NestingBoxPresencePeriod.objects.filter(
            chicken=chicken, ended_at__gt=recent_period.ended_at
        )
        .exclude(nesting_box=nesting_box)
        .exists()
    )
    if seen_elsewhere_since:
        return None
    return recent_period


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
