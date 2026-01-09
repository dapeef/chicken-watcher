from typing import Callable, Optional

from gpiozero import DigitalInputDevice
from gpiozero.exc import GPIOZeroError


class BeamSensor:
    def __init__(
        self,
        name: str,
        pin: int,
        *,
        pull_up: bool = True,
        bounce_time: float = 1,
    ):
        self.name = name
        self.pin = pin
        self.pull_up = pull_up
        self.bounce_time = bounce_time

        self.device: Optional[DigitalInputDevice] = None
        self.callback: Optional[Callable[[str, bool], None]] = None

    def connect(self) -> bool:
        """Initialise gpiozero device. Returns True on success."""
        try:
            self.device = DigitalInputDevice(
                self.pin,
                pull_up=self.pull_up,
                bounce_time=self.bounce_time,
            )
            print(f"[{self.name}] Connected to beam sensor on GPIO {self.pin}")
            return True
        except (GPIOZeroError, ValueError) as exc:
            print(f"[{self.name}] Error connecting to GPIO {self.pin}: {exc}")
            return False

    def disconnect(self) -> None:
        """Tear everything down."""
        self.stop_reading()
        if self.device:
            self.device.close()
            self.device = None
            print(f"[{self.name}] Disconnected from GPIO {self.pin}")

    def start_reading(self, callback: Callable[[str], None]) -> None:
        """
        Register a callback that is invoked on every state change.

        callback arguments:
            name   – sensor name
            broken – True  → beam broken  (falling edge with pull-up)
                      False → beam intact   (rising edge with pull-up)
        """
        if not self.device:
            raise RuntimeError("Call connect() successfully before start_reading().")

        self.callback = callback
        self.device.when_activated = self.callback  # falling edge; beam broken
        print(f"[{self.name}] Started listening for beam events…")

    def stop_reading(self) -> None:
        """Remove event handlers."""
        if not self.device:
            return
        self.device.when_activated = None
        self.device.when_deactivated = None
        self.callback = None
        print(f"[{self.name}] Stopped listening for beam events.")
