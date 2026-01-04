# Thread-friendly wrapper around a “beam-break” / photo-interrupter sensor
# that is wired to a single Raspberry Pi GPIO input pin.
#
#  ▸ Signal levels
#      HIGH (≈ 3.3V) … beam *unbroken*
#      LOW  (≈ 0 V)        … beam *broken*
#
#  ▸ The class mirrors the style of USBCamera / RFIDReader:
#        sensor = BeamBreakSensor("gate-1", pin=17)
#        sensor.connect()
#        sensor.start_monitoring(my_callback)        # async, edge-triggered
#        …
#        sensor.disconnect()
#
#  ▸ The callback receives:  (sensor_name: str, beam_broken: bool)
#
#  ▸ A software debounce (default 1 s) suppresses spurious multiple
#    notifications that occur within the interval.
# ---------------------------------------------------------------------------

import time
from typing import Callable, Optional

try:
    import RPi.GPIO as GPIO
except ModuleNotFoundError:
    class _StubGPIO:
        BCM = BOARD = BOTH = IN = PUD_OFF = RISING = FALLING = 0

        def setmode(*_, **__):
            pass

        def setup(*_, **__):
            pass

        def input(*_, **__):
            return 1  # “beam unbroken”

        def add_event_detect(*_, **__):
            pass

        def remove_event_detect(*_, **__):
            pass

        def cleanup(*_, **__):
            pass

    GPIO = _StubGPIO()


class BeamBreakSensor:
    """
    Beam-break sensor (digital) attached to a Raspberry Pi GPIO pin.

    The sensor keeps the line HIGH while the infrared/light beam is present
    and pulls it LOW when the beam is interrupted.  No additional pull-up /
    pull-down resistor is required; therefore GPIO is configured with
    `PUD_OFF`.

    The user-supplied callback receives `(sensor_name, beam_broken: bool)`.
    """

    def __init__(
        self,
        name: str,
        pin: int,
        debounce: float = 1.0,
        bcm_mode: bool = True,
    ):
        """
        Parameters
        ----------
        name      – Identifier passed back in every callback.
        pin       – GPIO pin number (BCM numbering by default).
        debounce  – Minimum time in seconds between successive callbacks.
        bcm_mode  – Use BCM numbering (True) or BOARD numbering (False).
        """
        self.name = name
        self.pin = pin
        self.debounce = debounce
        self.bcm_mode = bcm_mode

        self.running = False
        self.callback: Optional[Callable[[str, bool], None]] = None
        self._last_event_ts = 0.0
        self._current_state: Optional[bool] = None  # True ⇒ beam broken

    # --------------------------------------------------------------------- #
    #  GPIO life-cycle                                                      #
    # --------------------------------------------------------------------- #
    def connect(self) -> bool:
        """Initialise GPIO and take the first reading."""
        try:
            GPIO.setmode(GPIO.BCM if self.bcm_mode else GPIO.BOARD)
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)

            self._current_state = not GPIO.input(self.pin)  # LOW → broken
            print(
                f"[{self.name}] Connected on GPIO{self.pin} "
                f"(initial state: {'BROKEN' if self._current_state else 'CLEAR'})"
            )
            return True
        except RuntimeError as e:
            print(f"[{self.name}] GPIO initialisation failed: {e}")
            return False

    def disconnect(self) -> None:
        """Stop monitoring and release the pin."""
        self.stop_monitoring()
        GPIO.cleanup(self.pin)
        print(f"[{self.name}] Disconnected from GPIO{self.pin}")

    # --------------------------------------------------------------------- #
    #  One-shot read                                                        #
    # --------------------------------------------------------------------- #
    def read_state(self) -> Optional[bool]:
        """
        Synchronously read the line.

        Returns
        -------
        True     – beam is broken
        False    – beam is clear
        None     – error / GPIO not initialised
        """
        try:
            return not GPIO.input(self.pin)  # inverted logic
        except RuntimeError:
            return None

    # --------------------------------------------------------------------- #
    #  Asynchronous monitoring                                              #
    # --------------------------------------------------------------------- #
    def _edge_callback(self, _pin: int) -> None:
        """Internal: called by RPi.GPIO on *both* edges."""
        now = time.monotonic()
        if now - self._last_event_ts < self.debounce:
            return  # debounce

        self._last_event_ts = now
        self._current_state = not GPIO.input(self.pin)  # LOW → broken

        if self.callback:
            self.callback(self.name, self._current_state)

    def start_monitoring(
        self,
        callback: Callable[[str, bool], None],
        debounce: Optional[float] = None,
    ) -> None:
        """
        Begin edge-triggered monitoring (non-blocking).

        Parameters
        ----------
        callback – Function that receives `(name, beam_broken: bool)`.
        debounce – Optional override of the instance’s debounce time (seconds).
        """
        if debounce is not None:
            self.debounce = debounce

        self.callback = callback

        GPIO.add_event_detect(
            self.pin,
            GPIO.BOTH,  # rising & falling edges
            callback=self._edge_callback,
            bouncetime=int(self.debounce * 1000),
        )

        self.running = True  # kept for symmetry with stop_monitoring()
        print(
            f"[{self.name}] Started monitoring on GPIO{self.pin} "
            f"(debounce {self.debounce}s)"
        )

    def stop_monitoring(self) -> None:
        """Remove edge detection and stop raising callbacks."""
        if not self.running:
            return
        self.running = False
        GPIO.remove_event_detect(self.pin)

    # --------------------------------------------------------------------- #
    #  Quick CLI test                                                       #
    # --------------------------------------------------------------------- #
    @staticmethod
    def test(pin: int = 1) -> None:
        """
        Simple command-line helper:

            $ python -m utils.beam_break

        Press Ctrl-C to exit.
        """
        sensor = BeamBreakSensor("TEST", pin)
        if not sensor.connect():
            return

        def _printer(name: str, broken: bool):
            print(f"[{name}] {'BROKEN' if broken else 'CLEAR'}")

        sensor.start_monitoring(_printer)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            sensor.disconnect()


# Allow execution via `python beam_break.py`
if __name__ == "__main__":
    BeamBreakSensor.test()
