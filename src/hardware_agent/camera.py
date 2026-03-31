import logging
import threading
import time
from typing import Tuple

import cv2

from hardware_agent.base import BaseSensor

logger = logging.getLogger(__name__)


class USBCamera(BaseSensor):
    """
    Thread-friendly wrapper around an OpenCV VideoCapture device.
    The callback receives `(camera_name, frame)` where `frame` is a
    NumPy ndarray in BGR format (OpenCV default).
    """

    def __init__(
        self,
        name: str,
        device: str = 0,
        resolution: Tuple[int, int] = (1920, 1080),
        fps: int = 30,
    ):
        super().__init__(name)
        try:
            self.device = int(device)
        except ValueError:
            self.device = device
        self.resolution = resolution
        self.fps = fps

        self.cap = None  # cv2.VideoCapture instance
        self._frame_interval = 1.0 / fps
        self._next_ts = 0

        self._latest_frame = None
        self._read_lock = threading.Lock()

    def connect(self) -> bool:
        # Pick the proper backend: on Linux force V4L2 for strings,
        # otherwise leave CAP_ANY so OpenCV can guess for integers.
        backend = cv2.CAP_V4L2 if isinstance(self.device, str) else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(self.device, backend)

        if not self.cap.isOpened():
            logger.error("Could not open camera #%s", self.device)
            return False

        w, h = self.resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        # Don't set hardware FPS too low, as many cameras don't support it
        # even if we want to poll at a lower rate.
        hw_fps = max(self.fps, 15)
        self.cap.set(cv2.CAP_PROP_FPS, hw_fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        logger.info(
            "Connected to camera #%s (%dx%d @ %.1f hw fps)",
            self.device,
            int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            self.cap.get(cv2.CAP_PROP_FPS),
        )
        return True

    def disconnect(self):
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            logger.info("Disconnected camera #%s", self.device)
        self.cap = None

    def is_connected(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def on_connect(self):
        self._next_ts = time.perf_counter()
        self._latest_frame = None
        # Start a background thread to keep the camera buffer fresh.
        # This prevents the ~6 second lag often seen with OpenCV's default buffering.
        thread = threading.Thread(
            target=self._reader, name=f"CameraReader-{self.name}", daemon=True
        )
        thread.start()

    def _reader(self):
        """Background thread that constantly reads frames from the camera."""
        logger.info("Reader thread started")
        consecutive_failures = 0
        while self.running:
            cap = self.cap
            if cap is None or not cap.isOpened():
                break

            try:
                ok, frame = cap.read()
                if ok:
                    consecutive_failures = 0
                    with self._read_lock:
                        self._latest_frame = frame
                else:
                    if not self.running:
                        break

                    consecutive_failures += 1
                    if consecutive_failures >= 10:
                        logger.warning(
                            "Reader thread: failed to read frame 10 times in a row. Exiting."
                        )
                        break

                    # Wait a bit before retrying
                    time.sleep(0.1)
            except Exception as e:
                if self.running:
                    logger.error("Reader thread exception: %s", e)
                break

        # If we exited the loop but are still supposed to be running,
        # clear the latest frame so poll() knows something is wrong.
        if self.running:
            with self._read_lock:
                self._latest_frame = None
        logger.info("Reader thread stopped")

    def poll(self):
        # Wait for at least one frame to be available (useful at startup)
        start_wait = time.perf_counter()
        while self.read_frame() is None:
            if time.perf_counter() - start_wait > 5.0:
                raise Exception("Timed out waiting for first frame from camera")
            if not self.running:
                return
            time.sleep(0.1)

        frame = self.read_frame()
        if self.callback:
            self.callback(self.name, frame)

        # Soft frame-rate limiter
        self._next_ts += self._frame_interval
        time.sleep(max(0, self._next_ts - time.perf_counter()))

    def read_frame(self):
        with self._read_lock:
            return self._latest_frame

    @staticmethod
    def list_devices(max_indices: int = 10) -> None:
        """
        Try opening /dev/videoN (Linux) or index N (Windows/macOS) in a loop.
        Prints indices that succeed.
        """
        logger.info("Available video devices:")
        for idx in range(max_indices):
            cap = cv2.VideoCapture(idx, cv2.CAP_ANY)
            if cap.isOpened():
                logger.info("  #%d", idx)
                cap.release()
