"""
HardwareManager — orchestrates the set of hardware sensors.

Every sensor follows the same lifecycle:

  1. Validate its configuration (port, device, GPIO pin, etc.).
     If invalid, report a disconnected status and skip.
  2. Build the concrete sensor instance.
  3. Register with the manager (append to the sensor list).
  4. Start the sensor with an event handler and a status callback.

Each sensor kind has a fixed prefix (``rfid_``, ``camera_``, ``beam_``)
that is used when reporting status — ``report_status("rfid_left_1", ...)``.
The per-kind ``add_*`` methods differ only in what inputs they validate;
the post-validation registration path is shared via :meth:`_register`.
"""

import logging
from collections.abc import Callable

from hardware_agent.base import BaseSensor
from hardware_agent.beam_break_sensor import BeamSensor
from hardware_agent.camera import USBCamera
from hardware_agent.rfid_reader import RFIDReader
from web_app.services.hardware_events import (
    handle_beam_break,
    handle_camera_frame,
    handle_tag_read,
    report_status,
)

logger = logging.getLogger(__name__)

# How long to wait per-sensor when stopping.
STOP_TIMEOUT_PER_SENSOR = 5.0

# Sensor-kind prefixes used in HardwareSensor.name rows.
# e.g. an RFID reader called "left_1" becomes HardwareSensor "rfid_left_1".
RFID_PREFIX = "rfid"
CAMERA_PREFIX = "camera"
BEAM_PREFIX = "beam"


class HardwareManager:
    def __init__(self):
        self.sensors: list[BaseSensor] = []

    # ------------------------------------------------------------------
    # Per-kind add_* entry points.
    #
    # Each method validates its own required inputs and, if valid,
    # constructs the concrete sensor and delegates to _register for the
    # shared registration/start plumbing. This keeps the inevitable
    # per-kind validation differences explicit while removing the
    # duplicated "append + start + status lambda" tail.
    # ------------------------------------------------------------------

    def add_rfid_reader(self, name: str, port: str, reset_line: str = "dtr") -> None:
        if not port:
            self._skip(RFID_PREFIX, name, "No port provided", "No port configured")
            return

        reader = RFIDReader(name, port, reset_line=reset_line)
        self._register(RFID_PREFIX, reader, handle_tag_read)

    def add_camera(self, name: str, device: str) -> None:
        if not device:
            self._skip(CAMERA_PREFIX, name, "No device provided", "No device configured")
            return

        camera = USBCamera(name, device=device, fps=1)
        self._register(CAMERA_PREFIX, camera, handle_camera_frame)

    def add_beam_sensor(self, name: str, gpio: str, pin_factory) -> None:
        if not pin_factory:
            self._skip(
                BEAM_PREFIX,
                name,
                "No pin factory available",
                "LGPIO not available",
            )
            return

        if not gpio:
            self._skip(BEAM_PREFIX, name, "No GPIO provided", "No GPIO configured")
            return

        try:
            pin = int(gpio)
        except (ValueError, TypeError):
            self._skip(
                BEAM_PREFIX,
                name,
                f"Invalid GPIO '{gpio}'",
                f"Invalid GPIO: {gpio}",
            )
            return

        beam = BeamSensor(name, pin, pin_factory=pin_factory)
        self._register(BEAM_PREFIX, beam, handle_beam_break)

    # ------------------------------------------------------------------
    # Shared plumbing
    # ------------------------------------------------------------------

    def _register(
        self,
        prefix: str,
        sensor: BaseSensor,
        handler: Callable,
    ) -> None:
        """Append ``sensor`` to the managed set and start it with a
        status callback bound to the given ``prefix``.

        Called by every ``add_*`` method once the concrete sensor has
        been constructed. The status callback translates bare sensor
        names (``"left_1"``) into prefixed :class:`HardwareSensor` row
        names (``"rfid_left_1"``) so the dashboard can tell RFID status
        apart from camera status even when names collide.
        """
        self.sensors.append(sensor)
        sensor.start(
            handler,
            status_callback=lambda n, c, m="": report_status(f"{prefix}_{n}", c, m),
        )

    def _skip(
        self,
        prefix: str,
        name: str,
        log_reason: str,
        status_message: str,
    ) -> None:
        """Record a "we did not start this sensor" outcome.

        Emits a WARNING log with the human-friendly reason and writes
        a disconnected :class:`HardwareSensor` row so the dashboard
        surfaces the misconfiguration instead of silently missing a
        device.
        """
        human_kind = {
            RFID_PREFIX: "RFID reader",
            CAMERA_PREFIX: "camera",
            BEAM_PREFIX: "beam sensor",
        }.get(prefix, prefix)
        logger.warning("Skipping %s '%s': %s", human_kind, name, log_reason)
        report_status(f"{prefix}_{name}", False, status_message)

    def stop_all(self, timeout: float = STOP_TIMEOUT_PER_SENSOR) -> None:
        """Stop every registered sensor and release its resources.

        Called from the SIGTERM/SIGINT handler in ``service.run_agent``.
        Iterates through ``self.sensors`` in insertion order, asking each
        to stop and join its worker thread with ``timeout`` seconds.
        Individual failures are logged but do not stop the iteration —
        we want a best-effort attempt to release every sensor's
        hardware handles before the process exits.
        """
        logger.info("Stopping %d sensors", len(self.sensors))
        for sensor in self.sensors:
            try:
                sensor.stop(timeout=timeout)
            except Exception as e:
                logger.error("Error stopping sensor %s: %s", sensor.name, e)
        logger.info("All sensors stopped")
