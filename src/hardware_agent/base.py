import threading
import time
from abc import ABC, abstractmethod
from typing import Callable, Optional


class BaseSensor(ABC):
    def __init__(self, name: str):
        self.name = name
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.callback: Optional[Callable] = None
        self.status_callback: Optional[Callable[[str, bool, str], None]] = None

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the hardware. Returns True on success."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the hardware."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the hardware is currently connected."""
        pass

    def start(
        self,
        callback: Callable,
        status_callback: Optional[Callable[[str, bool, str], None]] = None,
    ):
        """Start the sensor's background thread."""
        self.callback = callback
        self.status_callback = status_callback
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the sensor's background thread and disconnect."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        self.disconnect()

    def _run_loop(self):
        """Standard reconnection loop."""
        print(f"[{self.name}] Started background loop…")
        while self.running:
            if not self.is_connected():
                if self.connect():
                    if self.status_callback:
                        self.status_callback(self.name, True)
                    self.on_connect()
                else:
                    if self.status_callback:
                        self.status_callback(self.name, False, "Disconnected")
                    time.sleep(5)
                    continue

            try:
                self.poll()
            except Exception as e:
                print(f"[{self.name}] Error in loop: {e}")
                if self.status_callback:
                    self.status_callback(self.name, False, str(e))
                self.handle_error(e)
                time.sleep(5)

    @abstractmethod
    def poll(self):
        """Perform one iteration of work (reading data)."""
        pass

    def on_connect(self):
        """Hook called immediately after a successful connection."""
        pass

    def handle_error(self, exc: Exception):
        """Handle an exception occurred during poll. Default is to disconnect."""
        self.disconnect()
