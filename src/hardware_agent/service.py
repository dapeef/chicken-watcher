import os
import time

from hardware_agent.rfid_reader import RFIDReader

def handle_tag_read(name: str, tag: str):
    print(name, tag)

def main():
    rfid_reader = RFIDReader("left", os.environ.get("RFID_SERIAL_PORT_LEFT"))

    rfid_reader.connect()

    rfid_reader.start_reading(handle_tag_read)

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
