import serial
from serial.tools import list_ports

PORT = "/dev/tty.usbserial-BG01PVA3"   # use the tty.* variant if cu.* is silent
BAUD = 9600                            # confirmed by miniterm
STX, ETX = 0x02, 0x03

def open_reader():
    return serial.Serial(
        PORT, BAUD,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.2
    )

def recv_frame(ser):
    """read one STX … ETX frame, return payload (bytes) or None on timeout"""
    # throw away bytes until we see STX
    while True:
        b = ser.read(1)
        if not b:            # timeout
            return None
        if b[0] == STX:
            break

    payload = ser.read_until(bytes([ETX]))
    if not payload or payload[-1] != ETX:
        return None          # timed-out inside the frame
    return payload[:-1]      # strip ETX

def main():
    print("Ports:")
    for p in list_ports.comports():
        print(" ", p.device, p.description)
    print()

    with open_reader() as ser:
        print(f"Listening on {PORT} ({BAUD} baud) …  Ctrl-C to quit")
        while True:
            frame = recv_frame(ser)
            if not frame:
                continue                  # just a timeout

            tag    = frame[:-1].decode()  # last byte is a checksum

            print("Card:", tag)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass