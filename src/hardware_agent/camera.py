import logging
import threading
import time

import cv2

from hardware_agent.base import BaseSensor

logger = logging.getLogger(__name__)

# How long to wait for the reader thread to exit when disconnecting.
READER_JOIN_TIMEOUT = 2.0


class USBCamera(BaseSensor):
    """
    Thread-friendly wrapper around an OpenCV VideoCapture device.
    The callback receives ``(camera_name, frame)`` where ``frame`` is a
    NumPy ndarray in BGR format (OpenCV default).

    Implementation notes:

    * A **reader thread** (separate from ``BaseSensor._run_loop``) pulls
      frames continuously into ``self._latest_frame``. This keeps
      OpenCV's internal buffer from lagging by several seconds.
    * The reader thread is **tracked explicitly** so ``disconnect()``
      can signal it to stop and join it. Without this, each reconnect
      would spawn a fresh reader and leak the old one — thread count
      grew unbounded over hours of operation.
    * The reader is gated on a **per-connection stop event**
      (``_reader_stop``), distinct from the sensor-wide ``_stop_event``.
      This lets ``disconnect()`` end the reader without terminating
      the whole sensor — so a reconnect spawns a fresh reader cleanly.
    """

    def __init__(
        self,
        name: str,
        device: str = 0,
        resolution: tuple[int, int] = (1920, 1080),
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
        self._next_ts = 0.0

        self._latest_frame = None
        self._read_lock = threading.Lock()

        # Reader-thread bookkeeping. ``_reader_thread`` is the handle we
        # need to join on disconnect. ``_reader_stop`` is signalled to
        # break the reader out of its ``cap.read()`` loop.
        self._reader_thread: threading.Thread | None = None
        self._reader_stop = threading.Event()

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

    def disconnect(self) -> None:
        """Tear down the reader thread and release the OpenCV handle.

        Order matters:

        1. Signal the reader to stop (``_reader_stop.set()``) before
           doing anything to ``self.cap``, so the reader observes the
           shutdown signal before its next ``cap.read()``.
        2. Join the reader thread with a short timeout.
        3. Release the capture device.

        If the reader is holding ``cap.read()`` when we release the
        device, OpenCV's behaviour is undefined — joining first keeps
        us well-defined.
        """
        self._reader_stop.set()
        reader = self._reader_thread
        if reader is not None and reader.is_alive():
            reader.join(timeout=READER_JOIN_TIMEOUT)
            if reader.is_alive():
                logger.warning(
                    "[%s] reader thread did not exit within %.1fs",
                    self.name,
                    READER_JOIN_TIMEOUT,
                )
        self._reader_thread = None

        if self.cap is not None:
            if self.cap.isOpened():
                self.cap.release()
                logger.info("Disconnected camera #%s", self.device)
            self.cap = None

    def is_connected(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def on_connect(self) -> None:
        self._next_ts = time.perf_counter()
        with self._read_lock:
            self._latest_frame = None

        # Fresh per-connection stop event so this reader doesn't
        # inherit a prior (set) state.
        self._reader_stop = threading.Event()
        self._reader_thread = threading.Thread(
            target=self._reader,
            name=f"CameraReader-{self.name}",
            daemon=True,
        )
        self._reader_thread.start()

    def _reader(self) -> None:
        """Background thread that constantly reads frames from the camera."""
        logger.info("[%s] reader thread started", self.name)
        consecutive_failures = 0

        # Snapshot the cap and stop event at thread start so we don't
        # race with disconnect() blanking ``self.cap`` mid-read.
        cap = self.cap
        stop_event = self._reader_stop

        while not stop_event.is_set():
            if cap is None or not cap.isOpened():
                break

            try:
                ok, frame = cap.read()
            except Exception as e:
                if not stop_event.is_set():
                    logger.error("[%s] reader thread exception: %s", self.name, e)
                break

            if ok:
                consecutive_failures = 0
                with self._read_lock:
                    self._latest_frame = frame
                continue

            if stop_event.is_set():
                break

            consecutive_failures += 1
            if consecutive_failures >= 10:
                logger.warning(
                    "[%s] reader thread: 10 consecutive read failures — exiting",
                    self.name,
                )
                break

            # Short interruptible wait before retrying.
            if stop_event.wait(0.1):
                break

        # If we exited for an external reason (not a stop signal),
        # clear the last frame so poll() can surface the problem.
        if not stop_event.is_set():
            with self._read_lock:
                self._latest_frame = None
        logger.info("[%s] reader thread stopped", self.name)

    def poll(self) -> None:
        # Wait for at least one frame to be available (useful at startup)
        start_wait = time.perf_counter()
        while self.read_frame() is None:
            if time.perf_counter() - start_wait > 5.0:
                raise RuntimeError("Timed out waiting for first frame from camera")
            if self._stop_event.is_set():
                return
            # Interruptible wait — stop() can break us out immediately.
            if self._stop_event.wait(0.1):
                return

        frame = self.read_frame()
        if self.callback:
            self.callback(self.name, frame)

        # Soft frame-rate limiter. Use the stop event so a pending shutdown
        # can cut the wait short.
        self._next_ts += self._frame_interval
        wait_s = max(0.0, self._next_ts - time.perf_counter())
        if wait_s > 0:
            self._stop_event.wait(wait_s)

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
