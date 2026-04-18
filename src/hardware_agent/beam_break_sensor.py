import contextlib
import logging
import time
from typing import Any

from gpiozero import DigitalInputDevice
from gpiozero.exc import GPIOZeroError

from hardware_agent.base import BaseSensor

logger = logging.getLogger(__name__)


class BeamSensor(BaseSensor):
    def __init__(
        self,
        name: str,
        pin: int,
        *,
        pull_up: bool = True,
        bounce_time: float | None = None,
        pin_factory: Any = None,
    ):
        super().__init__(name)
        self.pin = pin
        self.pull_up = pull_up
        self.bounce_time = bounce_time
        self.pin_factory = pin_factory

        self.device: DigitalInputDevice | None = None

    def connect(self) -> bool:
        """Initialise gpiozero device. Returns True on success."""
        try:
            self.device = DigitalInputDevice(
                self.pin,
                pull_up=self.pull_up,
                bounce_time=self.bounce_time,
                pin_factory=self.pin_factory,
            )
            logger.info("Connected to beam sensor on GPIO %s", self.pin)
            return True
        except (GPIOZeroError, ValueError) as exc:
            logger.error("Error connecting to GPIO %s: %s", self.pin, exc)
            return False

    def disconnect(self) -> None:
        """Tear everything down."""
        if self.device:
            with contextlib.suppress(Exception):
                self.device.close()
            logger.info("Disconnected from GPIO %s", self.pin)
        self.device = None

    def is_connected(self) -> bool:
        return self.device is not None

    def on_connect(self):
        if self.device and self.callback:
            self.device.when_activated = lambda: self.callback(self.name)

    def poll(self):
        # Check if device is still valid. For GPIO, it's hard to tell
        # if it was unplugged unless we try to read it.
        if not self.device:
            return

        try:
            _ = self.device.value
        except Exception as e:
            raise RuntimeError(f"GPIO error: {e}") from e

        time.sleep(10)
