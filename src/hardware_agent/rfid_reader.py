import serial
from serial.tools import list_ports

import time
import threading
from typing import Callable, Optional


START_BYTE, END_BYTE = 0x02, 0x03
MIN_RESET_INTERVAL = 0.1  # Seconds


class RFIDReader:
    def __init__(self, name: str, port: str, baudrate: int = 9600, timeout: int = 1):
        self.name = name
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.running = False
        self.thread = None
        self.callback = None
        self.reset_interval = 1

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
            print(f"[{self.name}] Connected to RFID reader on {self.port}")
            return True
        except serial.SerialException as e:
            print(f"[{self.name}] Error connecting to {self.port}: {e}")
            return False

    def read_tag(self) -> Optional[str]:
        if not self.serial_conn or not self.serial_conn.is_open:
            return None

        try:
            frame = self.recv_frame()
            if not frame:
                return None  # just a timeout

            tag = frame[:-1].decode()  # last byte is a checksum

            return tag

        except Exception as e:
            print(f"[{self.name}] Error reading tag: {e}")
            return None

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

    def _read_loop(self):
        print(f"[{self.name}] Started listening for RFID tags...")

        while self.running:
            self.serial_conn.rts = False

            while True:
                tag = self.read_tag()

                if tag:
                    self.callback(self.name, tag)

                    # Reset reader so that it can read the same tag repeatedly
                    self.serial_conn.rts = True
                    time.sleep(max(MIN_RESET_INTERVAL, self.reset_interval))
                    self.serial_conn.rts = False

    def start_reading(
        self, callback: Callable[[str, str], None], reset_interval: float = 1
    ):
        self.callback = callback
        self.reset_interval = reset_interval

        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def stop_reading(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def disconnect(self):
        self.stop_reading()
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print(f"[{self.name}] Disconnected from {self.port}")

    @staticmethod
    def list_ports() -> None:
        print("Ports:")
        for p in list_ports.comports():
            print(" ", p.device, p.description)
        print()
