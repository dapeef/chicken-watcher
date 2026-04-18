import contextlib
import logging
import time

import serial
from serial.tools import list_ports

from hardware_agent.base import BaseSensor

logger = logging.getLogger(__name__)

START_BYTE, END_BYTE = 0x02, 0x03
MIN_RESET_INTERVAL = 0.1  # Seconds


class RFIDReader(BaseSensor):
    def __init__(
        self,
        name: str,
        port: str,
        baudrate: int = 9600,
        timeout: int = 1,
        reset_interval: float = 0.1,
    ):
        super().__init__(name)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.reset_interval = reset_interval
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

    def on_connect(self):
        if self.serial_conn:
            self.serial_conn.rts = False

    def poll(self):
        if not self.serial_conn:
            return

        tag = self.read_tag()
        if tag:
            if self.callback:
                self.callback(self.name, tag)

            # Reset reader so that it can read the same tag repeatedly
            self.serial_conn.rts = True
            time.sleep(max(MIN_RESET_INTERVAL, self.reset_interval))
            self.serial_conn.rts = False

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
