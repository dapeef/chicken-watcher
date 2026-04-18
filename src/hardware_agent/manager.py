import logging

from hardware_agent.beam_break_sensor import BeamSensor
from hardware_agent.camera import USBCamera
from hardware_agent.rfid_reader import RFIDReader
from hardware_agent.handlers import (
    report_status,
    handle_tag_read,
    handle_camera_frame,
    handle_beam_break,
)

logger = logging.getLogger(__name__)

# How long to wait per-sensor when stopping.
STOP_TIMEOUT_PER_SENSOR = 5.0


class HardwareManager:
    def __init__(self):
        self.sensors = []

    def add_rfid_reader(self, name: str, port: str):
        if not port:
            logger.warning("Skipping RFID reader '%s': No port provided", name)
            report_status(f"rfid_{name}", False, "No port configured")
            return

        reader = RFIDReader(name, port)
        self.sensors.append(reader)
        reader.start(
            handle_tag_read,
            status_callback=lambda n, c, m="": report_status(f"rfid_{n}", c, m),
        )

    def add_camera(self, name: str, device: str):
        if not device:
            logger.warning("Skipping camera '%s': No device provided", name)
            report_status(f"camera_{name}", False, "No device configured")
            return

        camera = USBCamera(name, device=device, fps=1)
        self.sensors.append(camera)
        camera.start(
            handle_camera_frame,
            status_callback=lambda n, c, m="": report_status(f"camera_{n}", c, m),
        )

    def add_beam_sensor(self, name: str, gpio: str, pin_factory):
        if not pin_factory:
            logger.warning("Skipping beam sensor '%s': No pin factory available", name)
            report_status(f"beam_{name}", False, "LGPIO not available")
            return

        if not gpio:
            logger.warning("Skipping beam sensor '%s': No GPIO provided", name)
            report_status(f"beam_{name}", False, "No GPIO configured")
            return

        try:
            pin = int(gpio)
        except (ValueError, TypeError):
            logger.warning("Skipping beam sensor '%s': Invalid GPIO '%s'", name, gpio)
            report_status(f"beam_{name}", False, f"Invalid GPIO: {gpio}")
            return

        beam = BeamSensor(name, pin, pin_factory=pin_factory)
        self.sensors.append(beam)
        beam.start(
            handle_beam_break,
            status_callback=lambda n, c, m="": report_status(f"beam_{n}", c, m),
        )

    def stop_all(self, timeout: float = STOP_TIMEOUT_PER_SENSOR) -> None:
        """Stop every registered sensor and release its resources.

        Called from the SIGTERM/SIGINT handler in ``service.run_agent``.
        Iterates through ``self.sensors`` in insertion order, asking each
        to stop and join its worker thread with ``timeout`` seconds.
        Individual failures are logged but do not stop the iteration —
        we want to make a best-effort attempt to release every
        sensor's hardware handles before the process exits.
        """
        logger.info("Stopping %d sensors", len(self.sensors))
        for sensor in self.sensors:
            try:
                sensor.stop(timeout=timeout)
            except Exception as e:
                logger.error("Error stopping sensor %s: %s", sensor.name, e)
        logger.info("All sensors stopped")
