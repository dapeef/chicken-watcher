import contextlib
import logging
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
        reset_line: str = "dtr",
    ):
        if reset_line not in VALID_RESET_LINES:
            raise ValueError(
                f"Invalid reset_line {reset_line!r}; must be one of {VALID_RESET_LINES}"
            )
        super().__init__(name)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.reset_interval = reset_interval
        self.reset_line = reset_line
        self.serial_conn = None

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

    def _set_modem_line(self, line: str, value: bool) -> None:
        """Set RTS or DTR with a small retry on transient OSError.

        Each modem-control assignment fires a USB control transfer to the
        USB-serial chip. On a marginal hub these can fail with EPROTO
        (errno 71), particularly during the burst of activity at startup
        when several dongles are being initialised at once. Retrying a
        couple of times with a tiny pause clears the vast majority of
        these without escalating to a full disconnect/reconnect cycle.
        Persistent failures still raise so that BaseSensor can hand off
        to handle_error() and reconnect cleanly.
        """
        last_exc: Exception | None = None
        for attempt in range(self._MODEM_RETRY_ATTEMPTS):
            try:
                setattr(self.serial_conn, line, value)
                return
            except OSError as e:
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

    def on_connect(self):
        # Hold the configured reset line low at idle so it does not
        # accidentally hold the RFID PCB in reset when no tag is present.
        if self.serial_conn:
            self._set_modem_line(self.reset_line, False)

    def poll(self):
        if not self.serial_conn:
            return

        tag = self.read_tag()
        if tag:
            if self.callback:
                self.callback(self.name, tag)

            # Pulse the reset line so the reader can re-read the same tag.
            # A single modem-control line is used (configured via
            # reset_line) rather than both RTS and DTR: each assignment
            # fires a USB control transfer to the USB-serial chip, and
            # unnecessary transfers stress marginal hubs and can cause
            # EPROTO (errno 71). Bracketing with a buffer flush stops any
            # frame queued during the pulse from re-firing the callback as
            # a duplicate read.
            self._set_modem_line(self.reset_line, True)
            time.sleep(self.reset_interval)
            self._set_modem_line(self.reset_line, False)
            with contextlib.suppress(Exception):
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
        """read one STX … ETX frame, return payload (bytes) or None on timeout"""
        # throw away bytes until we see STX
        while True:
            b = self.serial_conn.read(1)
            if not b:  # timeout
                return None
            if b[0] == START_BYTE:
                break

        payload = self.serial_conn.read_until(bytes([END_BYTE]))
        if not payload or payload[-1] != END_BYTE:
            return None  # timed-out inside the frame
        return payload[:-1]  # strip ETX

    @staticmethod
    def list_ports() -> None:
        for p in list_ports.comports():
            logger.info("Port: %s %s", p.device, p.description)
