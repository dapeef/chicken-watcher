"""
Persists events emitted by the hardware agent.

This module is the seam between the physical-device code
(:mod:`hardware_agent`) and Django. The hardware agent detects things
(a tag was read, a beam was broken, a camera frame was captured) and
calls into the functions here, which translate them into model writes.

Everything in this file is **pure Django ORM** — no GPIO, OpenCV, or
serial I/O. It previously lived in ``hardware_agent/handlers.py`` which
made ``hardware_agent`` (conceptually a driver layer) transitively
depend on the web app's models. Splitting it out:

* Decouples the hardware agent from the web app — the agent can now be
  wired to any event sink via dependency injection.
* Keeps Django ORM code inside ``web_app`` where it's discoverable
  alongside the models it writes to.

Public API:

* :func:`handle_tag_read` — RFID tag observation.
* :func:`handle_beam_break` — beam-break event (records an egg).
* :func:`handle_camera_frame` — camera frame capture.
* :func:`report_status` — sensor connect/disconnect heartbeat.
* :func:`report_event` — generic "sensor just emitted something" ping.

The leading-underscore helpers exposed at module level
(``_record_tag_read``, ``_find_extensible_period``,
``_nesting_box_name_for_sensor``) are implementation details, kept
testable but not part of the stable API.
"""

import logging
import pathlib
import re
from datetime import datetime, timedelta

import cv2
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from web_app.models import (
    Chicken,
    Egg,
    HardwareSensor,
    NestingBox,
    NestingBoxImage,
    NestingBoxPresence,
    NestingBoxPresencePeriod,
    Tag,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sensor status / event reporting
# ---------------------------------------------------------------------------


def report_status(full_name: str, connected: bool, message: str = "") -> None:
    """Upsert a :class:`HardwareSensor` row with the current connection
    state and a bumped ``last_seen_at`` timestamp. Called by the
    hardware agent on every connect/disconnect cycle.

    Errors are swallowed and logged: status reporting must never take
    the sensor loop down.
    """
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


def report_event(full_name: str) -> None:
    """Mark a sensor as "just produced an event" by bumping
    ``last_event_at`` and setting ``is_connected=True``. Called by the
    event-handling functions below on every incoming signal.

    Errors are swallowed and logged.
    """
    try:
        HardwareSensor.objects.filter(name=full_name).update(
            last_event_at=timezone.now(), is_connected=True
        )
    except Exception as e:
        logger.error("Error reporting event for %s: %s", full_name, e)


# ---------------------------------------------------------------------------
# RFID tag reads
# ---------------------------------------------------------------------------

# An RFID read extends a prior period for the same chicken+box if the
# prior period ended within this many seconds of "now". Beyond that, a
# new period is started (the chicken has been away long enough that
# it's a fresh visit).
NESTING_BOX_PRESENCE_TIMEOUT = 60


def _nesting_box_name_for_sensor(sensor_name: str) -> str:
    """Derive the nesting box name from a sensor name.

    Sensors are named with a ``_<digit>`` suffix to distinguish multiple
    sensors in the same box (e.g. ``"left_1"``, ``"left_2"`` → ``"left"``).
    If the name has no such suffix the name itself is used as-is (e.g.
    ``"left"`` → ``"left"``).
    """
    match = re.fullmatch(r"(.+)_(\d+)$", sensor_name)
    if match:
        return match.group(1)
    return sensor_name


def handle_tag_read(name: str, tag: str) -> None:
    """Handle an RFID tag read event from a sensor named *name*.

    *name* is the sensor identifier (e.g. ``"left"``, ``"left_a"``,
    ``"left_b"``).  The corresponding nesting box is looked up by
    deriving the box name from *name* via
    :func:`_nesting_box_name_for_sensor`. The original sensor name is
    stored on the presence record so individual sensors can be
    distinguished on the timeline.

    Each nesting box has up to four RFID readers. Without coordination,
    concurrent reads of the same tag from different readers in the same
    box race each other: both transactions see "no recent period
    exists" and each INSERTs a fresh one, producing duplicates. We
    serialise on the ``Chicken`` row via ``select_for_update`` so only
    one handler at a time can extend-or-create a period for any given
    chicken.
    """
    # These two sit outside the transaction so an in-flight event is
    # still reported even if the per-read transaction rolls back.
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
    standard ``DoesNotExist`` exceptions if any lookup fails; they're
    caught and logged by the caller.

    The ``Chicken`` row is locked for update (``select_for_update``) at
    the start of the transaction. This serialises all handlers
    operating on the same chicken, so the period-extend-or-create logic
    executes without races. On SQLite ``select_for_update`` is a no-op
    but SQLite serialises all writes anyway, so correctness is
    preserved.
    """
    nesting_box = NestingBox.objects.get(name=box_name)
    tag_obj = Tag.objects.get(rfid_string=tag)

    # Lock the chicken row. Any concurrent handler reading the same
    # chicken will block here until we commit, guaranteeing a
    # consistent view of that chicken's presence periods for the
    # duration of this transaction.
    chicken = Chicken.objects.select_for_update().get(
        tag=tag_obj, date_of_death__isnull=True
    )

    now = timezone.now()

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
    """Return a :class:`NestingBoxPresencePeriod` for
    ``chicken``+``nesting_box`` that can be extended to ``now``, or
    ``None`` if a new period should be created.

    A period is extensible when:

    * it ended within :data:`NESTING_BOX_PRESENCE_TIMEOUT` seconds of
      ``now``, and
    * no later period exists for the same chicken in a different box
      (which would indicate the chicken left this box after that
      period ended).

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


# ---------------------------------------------------------------------------
# Camera frames
# ---------------------------------------------------------------------------


def save_frame_to_file(cam_name: str, frame) -> None:
    """Disk-only variant of :func:`save_frame_to_db` — used for local
    debugging / manual inspection, not in production."""
    frame_dir = pathlib.Path("frames")
    frame_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    file_name = frame_dir / f"{cam_name}_{ts}.jpg"
    cv2.imwrite(str(file_name), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])


def handle_camera_frame(name: str, frame) -> None:
    report_event(f"camera_{name}")
    save_frame_to_db(name, frame)


def save_frame_to_db(cam_name: str, frame) -> None:
    """
    Encode ``frame`` (a numpy array from ``cv2.VideoCapture.read()``) as
    JPEG and persist it as a :class:`NestingBoxImage`.

    The current deployment uses a single overhead camera that covers
    multiple nesting boxes (and some surrounding area), so images are
    stored unassociated with a specific box. The originating camera is
    recorded in the filename (``{cam_name}_{timestamp}.jpg``) so frames
    from multiple cameras would remain distinguishable if that ever
    changes.
    """
    success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not success:
        raise RuntimeError("Could not encode frame to JPEG")

    ts = datetime.now().strftime("%Y%m%dT%H%M%S%f")[:-3]
    filename = f"{cam_name}_{ts}.jpg"

    django_file = ContentFile(buffer.tobytes(), name=filename)
    NestingBoxImage.objects.create(image=django_file)

    logger.debug("%s frame saved to db as %s", cam_name, filename)


# ---------------------------------------------------------------------------
# Beam-break events
# ---------------------------------------------------------------------------


@transaction.atomic
def handle_beam_break(name: str) -> None:
    """Create an :class:`Egg` row for the chicken most recently seen in
    this box. The beam sensor fires when a hen leaves the box after
    laying — attributing the egg to whoever was just there."""
    report_event(f"beam_{name}")
    logger.info("[%s] Beam break detected", name)

    try:
        nesting_box = NestingBox.objects.get(name=name)

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
