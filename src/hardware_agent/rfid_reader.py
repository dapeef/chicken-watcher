import serial
import time
import threading
from typing import Callable, Optional


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
        self.debounce_time = 1.0
        self.last_tag = None
        self.last_time = 0

    def connect(self) -> bool:
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
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
            self.serial_conn.reset_input_buffer()
            data = self.serial_conn.readline()

            if data:
                tag_id = data.decode('utf-8').strip()
                return tag_id
            return None

        except Exception as e:
            print(f"[{self.name}] Error reading tag: {e}")
            return None

    def _read_loop(self):
        print(f"[{self.name}] Started listening for RFID tags...")

        while self.running:
            tag_id = self.read_tag()
            current_time = time.time()

            if tag_id and (tag_id != self.last_tag or
                           current_time - self.last_time > self.debounce_time):
                print(f"[{self.name}] Tag detected: {tag_id}")
                self.last_tag = tag_id
                self.last_time = current_time

                if self.callback:
                    self.callback(self.name, tag_id)

            time.sleep(0.1)

    def start_reading(self, callback: Callable[[str, str], None]):
        self.callback = callback
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