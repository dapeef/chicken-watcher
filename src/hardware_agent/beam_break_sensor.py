import threading
import time
from typing import Any, Callable, Optional

from gpiozero import DigitalInputDevice
from gpiozero.exc import GPIOZeroError
from gpiozero.pins.lgpio import LGPIOFactory

from hardware_agent.base import BaseSensor


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

        self.device: Optional[DigitalInputDevice] = None

    def connect(self) -> bool:
        """Initialise gpiozero device. Returns True on success."""
        try:
            self.device = DigitalInputDevice(
                self.pin,
                pull_up=self.pull_up,
                bounce_time=self.bounce_time,
                pin_factory=self.pin_factory,
            )
            print(f"[{self.name}] Connected to beam sensor on GPIO {self.pin}")
            return True
        except (GPIOZeroError, ValueError) as exc:
            print(f"[{self.name}] Error connecting to GPIO {self.pin}: {exc}")
            return False

    def disconnect(self) -> None:
        """Tear everything down."""
        if self.device:
            try:
                self.device.close()
            except:
                pass
            print(f"[{self.name}] Disconnected from GPIO {self.pin}")
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
            raise Exception(f"GPIO error: {e}")

        time.sleep(10)
