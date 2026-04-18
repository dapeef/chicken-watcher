import logging
import threading
from abc import ABC, abstractmethod
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# How long (in seconds) to wait between reconnect attempts when a sensor
# is disconnected or has errored. Made interruptible by waiting on
# ``self._stop_event`` rather than sleeping.
RECONNECT_INTERVAL_SECONDS = 5.0


class BaseSensor(ABC):
    """Base class for a single piece of hardware running its own
    background thread.

    Subclasses implement :meth:`connect`, :meth:`disconnect`,
    :meth:`is_connected`, and :meth:`poll`. The base handles the
    reconnect loop, status-callback plumbing, and a clean shutdown
    path driven by a ``threading.Event`` so that blocking sleeps
    during retry can be cancelled immediately.

    Lifecycle:

    * :meth:`start` — fire up the worker thread (non-blocking).
    * :meth:`stop` — signal the worker to exit, wait for it to join,
      then disconnect. Idempotent and safe to call multiple times.
    """

    def __init__(self, name: str):
        self.name = name
        # ``_stop_event`` is set when ``stop()`` is called. The run loop
        # checks it before every iteration and uses it to wait (instead
        # of ``time.sleep``) so shutdown is fast.
        self._stop_event = threading.Event()
        self._started = False
        self.thread: Optional[threading.Thread] = None
        self.callback: Optional[Callable] = None
        # status_callback(name, connected, message="") — message defaults
        # to an empty string, so both two-arg and three-arg call styles
        # are accepted.
        self.status_callback: Optional[Callable[..., None]] = None

    # ------------------------------------------------------------------
    # Backward-compatible ``running`` shim.
    #
    # Older tests and subclasses (notably USBCamera._reader) read/write
    # ``self.running`` directly. We expose it as a property wrapping
    # ``_stop_event`` so existing code keeps working without changes.
    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._started and not self._stop_event.is_set()

    @running.setter
    def running(self, value: bool) -> None:
        if value:
            self._stop_event.clear()
            self._started = True
        else:
            self._stop_event.set()

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the hardware. Returns True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the hardware."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the hardware is currently connected."""

    def start(
        self,
        callback: Callable,
        status_callback: Optional[Callable[..., None]] = None,
    ) -> None:
        """Start the sensor's background thread. Idempotent: calling
        twice is a no-op."""
        if self._started and self.thread is not None and self.thread.is_alive():
            logger.warning("Sensor %s already started; ignoring", self.name)
            return
        self.callback = callback
        self.status_callback = status_callback
        self._stop_event.clear()
        self._started = True
        self.thread = threading.Thread(
            target=self._run_loop, daemon=True, name=f"Sensor-{self.name}"
        )
        self.thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the sensor's background thread and disconnect.

        Signals the stop event (which interrupts any in-flight
        reconnect-backoff wait), joins the worker thread, then calls
        ``disconnect()`` to release hardware resources. Safe to call
        more than once.
        """
        self._stop_event.set()
        self._started = False
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=timeout)
            if self.thread.is_alive():
                logger.warning(
                    "Sensor %s thread did not exit within %.1fs", self.name, timeout
                )
        self.thread = None
        self.disconnect()

    def _run_loop(self) -> None:
        """Standard reconnection + poll loop."""
        logger.info("[%s] Started background loop", self.name)
        while not self._stop_event.is_set():
            if not self.is_connected():
                if self.connect():
                    if self.status_callback:
                        self.status_callback(self.name, True)
                    self.on_connect()
                else:
                    if self.status_callback:
                        self.status_callback(self.name, False, "Disconnected")
                    # Interruptible wait — stop() can cancel this within
                    # the event's resolution rather than waiting the full
                    # RECONNECT_INTERVAL_SECONDS.
                    if self._stop_event.wait(RECONNECT_INTERVAL_SECONDS):
                        break
                    continue

            try:
                self.poll()
            except Exception as e:
                logger.error("[%s] Error in loop: %s", self.name, e)
                if self.status_callback:
                    self.status_callback(self.name, False, str(e))
                self.handle_error(e)
                if self._stop_event.wait(RECONNECT_INTERVAL_SECONDS):
                    break
        logger.info("[%s] Background loop exited", self.name)

    @abstractmethod
    def poll(self) -> None:
        """Perform one iteration of work (reading data)."""

    def on_connect(self) -> None:
        """Hook called immediately after a successful connection."""

    def handle_error(self, exc: Exception) -> None:
        """Handle an exception occurred during poll. Default is to disconnect."""
        self.disconnect()
