import threading
import time
from typing import Any, Callable, Optional

from gpiozero import DigitalInputDevice
from gpiozero.exc import GPIOZeroError
from gpiozero.pins.lgpio import LGPIOFactory


class BeamSensor:
    def __init__(
        self,
        name: str,
        pin: int,
        *,
        pull_up: bool = True,
        bounce_time: float | None = None,
        pin_factory: LGPIOFactory | None = None,
    ):
        self.name = name
        self.pin = pin
        self.pull_up = pull_up
        self.bounce_time = bounce_time
        self.pin_factory = pin_factory

        self.device: Optional[DigitalInputDevice] = None
        self.callback: Optional[Callable[[str], None]] = None
        self.status_callback: Optional[Callable[[str, bool, str], None]] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None

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
        self.stop_reading()
        if self.device:
            self.device.close()
            self.device = None
            print(f"[{self.name}] Disconnected from GPIO {self.pin}")

    def _reconnect_loop(self):
        while self.running:
            if not self.device:
                if self.connect():
                    if self.status_callback:
                        self.status_callback(self.name, True)
                    if self.callback:
                        self.device.when_activated = lambda: self.callback(self.name)
                else:
                    if self.status_callback:
                        self.status_callback(self.name, False, "Disconnected")
                    time.sleep(5)
                    continue

            # Check if device is still valid. For GPIO, it's hard to tell
            # if it was unplugged unless we try to read it.
            try:
                _ = self.device.value
            except Exception as e:
                print(f"[{self.name}] GPIO error: {e}")
                if self.status_callback:
                    self.status_callback(self.name, False, str(e))
                self.device.close()
                self.device = None
                continue

            time.sleep(10)

    def start_reading(
        self,
        callback: Callable[[str], None],
        status_callback: Optional[Callable[[str, bool, str], None]] = None,
    ) -> None:
        """
        Register a callback that is invoked on every state change.
        """
        self.callback = callback
        self.status_callback = status_callback
        self.running = True
        self.thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self.thread.start()
        print(f"[{self.name}] Started listening for beam events…")

    def stop_reading(self) -> None:
        """Remove event handlers."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if not self.device:
            return
        self.device.when_activated = None
        self.device.when_deactivated = None
        self.callback = None
        print(f"[{self.name}] Stopped listening for beam events.")
