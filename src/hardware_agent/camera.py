import cv2
import time
import threading
from typing import Callable, Optional, Tuple, Union
import numpy as np


class USBCamera:
    """
    Thread-friendly wrapper around an OpenCV VideoCapture device.
    The callback receives `(camera_name, frame)` where `frame` is a
    NumPy ndarray in BGR format (OpenCV default).
    """

    def __init__(
        self,
        name: str,
        device: Union[int, str] = 0,
        resolution: Tuple[int, int] = (1920, 1080),
        fps: int = 30,
    ):
        self.name = name
        self.device = device
        self.resolution = resolution
        self.fps = fps

        self.cap = None  # cv2.VideoCapture instance
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.callback: Optional[Callable[[str, "np.ndarray"], None]] = None

        self._frame_interval = 1.0 / fps

    def connect(self) -> bool:
        # Pick the proper backend: on Linux force V4L2 for strings,
        # otherwise leave CAP_ANY so OpenCV can guess for integers.
        backend = cv2.CAP_V4L2 if isinstance(self.device, str) else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(self.device, backend)

        if not self.cap.isOpened():
            print(f"[{self.name}] Could not open camera #{self.device}")
            return False

        w, h = self.resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        print(
            f"[{self.name}] Connected to camera #{self.device} "
            f"({int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))}×"
            f"{int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ "
            f"{self.cap.get(cv2.CAP_PROP_FPS):.1f} fps)"
        )
        return True

    def disconnect(self):
        self.stop_capturing()
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            print(f"[{self.name}] Disconnected camera #{self.device}")

    def read_frame(self):
        if not self.cap or not self.cap.isOpened():
            return None
        ok, frame = self.cap.read()
        return frame if ok else None

    def _capture_loop(self):
        print(f"[{self.name}] Started capturing…")
        next_ts = time.perf_counter()
        while self.running:
            frame = self.read_frame()
            if frame is not None and self.callback:
                self.callback(self.name, frame)

            # Soft frame-rate limiter
            next_ts += self._frame_interval
            time.sleep(max(0, next_ts - time.perf_counter()))

    def start_capturing(self, callback: Callable[[str, "np.ndarray"], None]):
        if not self.cap or not self.cap.isOpened():
            raise RuntimeError("Camera not connected. Call connect() first.")

        self.callback = callback
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def stop_capturing(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    @staticmethod
    def list_devices(max_indices: int = 10) -> None:
        """
        Try opening /dev/videoN (Linux) or index N (Windows/macOS) in a loop.
        Prints indices that succeed.
        """
        print("Available video devices:")
        for idx in range(max_indices):
            cap = cv2.VideoCapture(idx, cv2.CAP_ANY)
            if cap.isOpened():
                print(f"  #{idx}")
                cap.release()
        print()
