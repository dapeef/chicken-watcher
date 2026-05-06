import contextlib
import logging
import threading
import time

import serial
from serial.tools import list_ports

from hardware_agent.base import BaseSensor

logger = logging.getLogger(__name__)

START_BYTE, END_BYTE = 0x02, 0x03

VALID_RESET_LINES = ("rts", "dtr")


class RFIDReader(BaseSensor):
    def __init__(
        self,
        name: str,
        port: str,
        baudrate: int = 9600,
        timeout: int = 1,
        reset_interval: float = 0.2,
        reset_line: str | None = "dtr",
    ):
        if reset_line is not None and reset_line not in VALID_RESET_LINES:
            raise ValueError(
                f"Invalid reset_line {reset_line!r}; must be one of {VALID_RESET_LINES} or None"
            )
        super().__init__(name)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.reset_interval = reset_interval
        self.reset_line = reset_line
        self.serial_conn = None
        # Pausing holds the reader in hardware reset between scan-group
        # slots. When _paused is set, poll() returns immediately without
        # reading; the coordinator calls pause()/resume() to transition.
        self._paused = threading.Event()

    def connect(self) -> bool:
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            logger.info("Connected to RFID reader on %s", self.port)
            return True
        except serial.SerialException as e:
            logger.error("Error connecting to %s: %s", self.port, e)
            return False

    def disconnect(self):
        if self.serial_conn and self.serial_conn.is_open:
            with contextlib.suppress(Exception):
                self.serial_conn.close()
            logger.info("Disconnected from %s", self.port)
        self.serial_conn = None

    def is_connected(self) -> bool:
        return self.serial_conn is not None and self.serial_conn.is_open

    # Backoff (seconds) between retry attempts when a modem-control write
    # transiently fails. Short enough to be invisible on a healthy bus,
    # long enough to let a marginal hub settle before retrying.
    _MODEM_RETRY_BACKOFF = 0.05
    _MODEM_RETRY_ATTEMPTS = 3

    def _set_modem_line(self, line: str, value: bool) -> bool:
        """Set RTS or DTR with a small retry on transient OSError.

        Each modem-control assignment fires a USB control transfer to the
        USB-serial chip. On a marginal hub these can fail with EPROTO
        (errno 71), particularly during the burst of activity at startup
        when several dongles are being initialised at once. Retrying a
        couple of times with a tiny pause clears the vast majority of
        these without escalating to a full disconnect/reconnect cycle.
        Persistent failures still raise so that BaseSensor can hand off
        to handle_error() and reconnect cleanly.

        Returns True if the assignment succeeded on the first attempt,
        False if it eventually succeeded after one or more retries.
        Callers that need a clean USB init (e.g. on_connect) can treat
        a False return as a signal to force a fresh connect cycle.
        """
        last_exc: Exception | None = None
        for attempt in range(self._MODEM_RETRY_ATTEMPTS):
            try:
                # Re-read serial_conn on every attempt: disconnect() running
                # in the reader's thread can set it to None at any point,
                # including between the caller's guard and this setattr.
                conn = self.serial_conn
                if conn is None:
                    return True  # nothing to do; treat as a clean success
                setattr(conn, line, value)
                return attempt == 0
            except (OSError, AttributeError) as e:
                # AttributeError covers the TOCTOU race where serial_conn
                # is set to None by disconnect() between our snapshot and
                # the setattr completing.
                if isinstance(e, AttributeError):
                    return True  # port gone; nothing to assert, treat as clean
                last_exc = e
                logger.warning(
                    "[%s] %s=%s failed (attempt %d/%d): %s",
                    self.name,
                    line,
                    value,
                    attempt + 1,
                    self._MODEM_RETRY_ATTEMPTS,
                    e,
                )
                time.sleep(self._MODEM_RETRY_BACKOFF)
        # Exhausted retries — re-raise the last exception so the loop can
        # disconnect + reconnect.
        assert last_exc is not None
        raise last_exc

    def pause(self) -> None:
        """Hold the reader in hardware reset until resume() is called.

        Before asserting the reset line, drains and delivers any tag frame
        already sitting in the OS receive buffer. A frame can arrive there
        in the window between the coordinator deciding to pause this reader
        and the reset line actually being asserted — without this drain it
        would sit in the buffer until the next resume() and only be
        delivered then, introducing unnecessary latency.

        After draining, asserts the reset line (if configured) and sets the
        paused flag so poll() becomes a no-op for the duration.

        Safe to call from any thread.
        """
        # Drain any complete frame already buffered before we lock the reader
        # out. read_tag() is non-blocking when there is nothing in the buffer
        # (recv_frame times out immediately and returns None), so this adds
        # negligible overhead in the common case.
        if self.serial_conn and not self._paused.is_set():
            with contextlib.suppress(Exception):
                tag = self.read_tag()
                if tag and self.callback:
                    self.callback(self.name, tag)

        self._paused.set()
        if self.serial_conn and self.reset_line is not None:
            with contextlib.suppress(OSError):
                self._set_modem_line(self.reset_line, True)

    def resume(self) -> None:
        """Release the reader from hardware reset and re-enable polling.

        Deasserts the reset line (if configured) then clears the paused
        flag so the next poll() call reads normally. Safe to call from
        any thread.
        """
        if self.serial_conn and self.reset_line is not None:
            with contextlib.suppress(OSError):
                self._set_modem_line(self.reset_line, False)
        self._paused.clear()

    # Exception raised when on_connect detects an unstable USB init.
    # Caught by BaseSensor._run_loop and triggers a clean reconnect.
    class UnstableInitError(OSError):
        """Raised when modem-control lines needed retries during on_connect.

        Even though the retries eventually succeeded, an RFID reader that
        experienced a troubled USB init often ends up in a firmware state
        where it silently fails to report tags.  Raising here causes
        BaseSensor to disconnect and reconnect, giving the USB stack and
        the reader firmware a clean slate.
        """

    def on_connect(self):
        if not self.serial_conn:
            return
        clean = True
        if self.reset_line is not None:
            # Pulse mode: hold the active line low at idle so it does not
            # accidentally hold the RFID PCB in reset between reads.
            clean &= self._set_modem_line(self.reset_line, False)
        else:
            # No-reset mode: pin *both* lines low. We don't know which one
            # is wired to RST on this adapter, and the kernel/pyserial does
            # not guarantee an initial state, so drive both to be safe.
            clean &= self._set_modem_line("rts", False)
            clean &= self._set_modem_line("dtr", False)
        if not clean:
            raise self.UnstableInitError(
                f"[{self.name}] modem-control lines required retries during init; "
                "reconnecting for a clean USB state"
            )

    # Maximum number of bytes to discard while hunting for STX before
    # giving up and treating the stream as corrupt. A valid tag frame is
    # at most ~20 bytes (STX + 12 tag chars + 1 checksum + ETX), so
    # anything beyond a couple of frames' worth of garbage indicates the
    # reader's firmware or the OS buffer is in a bad state.
    _MAX_SYNC_BYTES = 64

    def poll(self):
        if not self.serial_conn:
            return
        if self._paused.is_set():
            # Block until unpaused or the stop event fires, whichever comes
            # first. Without this the run loop spins at full CPU speed for
            # every paused reader — one tight loop per thread with no
            # blocking I/O to yield on.
            # Use _stop_event.wait so that stop() wakes this immediately
            # rather than waiting up to reset_interval to notice.
            self._stop_event.wait(timeout=self.reset_interval)
            # Check the port is still alive after the wait. A paused reader
            # never calls read(), so without this check a disconnection
            # (e.g. hub unplugged) would go unnoticed until the next
            # rotation cycle — every other reader surfaces the error
            # immediately through a failed read, but paused readers would
            # silently appear connected. Raising here lets _run_loop's
            # error handler trigger a clean disconnect/reconnect on the
            # same schedule as the active readers.
            if self.serial_conn and not self.serial_conn.is_open:
                raise OSError(f"[{self.name}] serial port closed while paused")
            return

        tag = self.read_tag()
        if tag:
            if self.callback:
                self.callback(self.name, tag)

            if self.reset_line is not None:
                # Pulse the reset line so the reader can re-read the same tag.
                # A single modem-control line is used (configured via
                # reset_line) rather than both RTS and DTR: each assignment
                # fires a USB control transfer to the USB-serial chip, and
                # unnecessary transfers stress marginal hubs and can cause
                # EPROTO (errno 71).
                #
                # try/finally guarantees the line is deasserted even if the
                # trailing _set_modem_line call fails: without this the reader
                # would be held in reset across the full reconnect backoff,
                # silently blocking all reads until the next on_connect.
                self._set_modem_line(self.reset_line, True)
                try:
                    time.sleep(self.reset_interval)
                finally:
                    self._set_modem_line(self.reset_line, False)

                # Flush any bytes queued during the reset pulse so they can't
                # be mistaken for the start of the next tag frame. This is
                # intentionally outside the try/finally: if flush fails we
                # want the exception to propagate so BaseSensor triggers a
                # clean disconnect/reconnect rather than leaving a dirty
                # buffer that silently corrupts subsequent reads.
                self.serial_conn.reset_input_buffer()

    def read_tag(self) -> str | None:
        if not self.serial_conn or not self.serial_conn.is_open:
            return None

        frame = self.recv_frame()
        if not frame:
            return None  # just a timeout

        tag = frame[:-1].decode()  # last byte is a checksum
        return tag

    def recv_frame(self):
        """Read one STX…ETX frame; return payload bytes or None on timeout.

        Discards bytes until STX (0x02) is found, then reads until ETX
        (0x03).  If more than _MAX_SYNC_BYTES are consumed before an STX
        appears the stream is considered corrupt and RuntimeError is raised
        so that BaseSensor's error handler can disconnect and reconnect,
        clearing both the OS buffer and the reader's firmware state.
        """
        # Discard bytes until we see STX, but give up after too many: a
        # garbage-filled buffer (e.g. from a partial reset) would otherwise
        # spin silently, consuming stale bytes one at a time while the
        # reader transmits valid frames that pile up behind them.
        for _ in range(self._MAX_SYNC_BYTES):
            b = self.serial_conn.read(1)
            if not b:  # timeout — no data, nothing to do
                return None
            if b[0] == START_BYTE:
                break
        else:
            raise RuntimeError(
                f"[{self.name}] stream corrupt: no STX in {self._MAX_SYNC_BYTES} bytes; "
                "reconnecting to clear buffer"
            )

        payload = self.serial_conn.read_until(bytes([END_BYTE]))
        if not payload or payload[-1] != END_BYTE:
            return None  # timed-out inside the frame
        return payload[:-1]  # strip ETX

    @staticmethod
    def list_ports() -> None:
        for p in list_ports.comports():
            logger.info("Port: %s %s", p.device, p.description)


class RFIDResetHolder(BaseSensor):
    """Holds an RFID reader permanently in reset via DTR.

    Opens the serial port and immediately asserts DTR high, keeping the
    reader's RST pin active for as long as the process runs.  poll() is
    a no-op — the reader never transmits while held in reset.

    This is a debugging aid for isolating RF interference between adjacent
    readers.  Use RFIDReader for normal operation.
    """

    def __init__(self, name: str, port: str):
        super().__init__(name)
        self.port = port
        self.serial_conn = None

    def connect(self) -> bool:
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=9600,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            logger.info("[%s] Opened port %s (held in reset)", self.name, self.port)
            return True
        except serial.SerialException as e:
            logger.error("[%s] Error opening %s: %s", self.name, self.port, e)
            return False

    def disconnect(self):
        if self.serial_conn and self.serial_conn.is_open:
            with contextlib.suppress(Exception):
                self.serial_conn.close()
            logger.info("[%s] Closed port %s", self.name, self.port)
        self.serial_conn = None

    def is_connected(self) -> bool:
        return self.serial_conn is not None and self.serial_conn.is_open

    def on_connect(self):
        # Assert DTR high to hold the reader's RST pin active.
        if self.serial_conn:
            with contextlib.suppress(OSError):
                self.serial_conn.dtr = True

    def poll(self):
        # Nothing to do — reader is held in reset and will not transmit.
        pass
