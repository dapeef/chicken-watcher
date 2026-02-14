import serial
from hardware_agent.rfid_reader import RFIDReader


class MockSerial:
    def __init__(self, data_to_read=None):
        self.data_to_read = data_to_read or b""
        self.is_open = True
        self.rts = False
        self.close_called = False

    def read(self, size=1):
        if not self.data_to_read:
            return b""
        res = self.data_to_read[:size]
        self.data_to_read = self.data_to_read[size:]
        return res

    def read_until(self, terminator=b"\n"):
        if terminator not in self.data_to_read:
            res = self.data_to_read
            self.data_to_read = b""
            return res
        idx = self.data_to_read.find(terminator) + len(terminator)
        res = self.data_to_read[:idx]
        self.data_to_read = self.data_to_read[idx:]
        return res

    def close(self):
        self.is_open = False
        self.close_called = True


def test_rfid_reader_connect_success(mocker):
    mock_serial = mocker.patch("serial.Serial", return_value=MockSerial())
    reader = RFIDReader("test", "/dev/ttyUSB0")
    assert reader.connect() is True
    assert reader.is_connected() is True
    mock_serial.assert_called_once()


def test_rfid_reader_connect_fail(mocker):
    mocker.patch("serial.Serial", side_effect=serial.SerialException("Failed"))
    reader = RFIDReader("test", "/dev/ttyUSB0")
    assert reader.connect() is False
    assert reader.is_connected() is False


def test_rfid_reader_recv_frame(mocker):
    # Frame: STX (0x02) + "ABC" + ETX (0x03)
    data = b"\xff\xfe\x02ABC\x03\xaa"
    mock_conn = MockSerial(data)
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = mock_conn

    frame = reader.recv_frame()
    assert frame == b"ABC"
    # Check that it consumed up to ETX
    assert mock_conn.data_to_read == b"\xaa"


def test_rfid_reader_read_tag(mocker):
    # Tag frame including checksum byte before ETX
    # Wait, looking at rfid_reader.py:
    # tag = frame[:-1].decode()  # last byte is a checksum
    # recv_frame returns payload without ETX.
    # So if frame is "TAG123" + checksum, tag is "TAG123"
    data = b"\x02TAG123X\x03"
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = MockSerial(data)

    tag = reader.read_tag()
    assert tag == "TAG123"


def test_rfid_reader_poll(mocker):
    data = b"\x02TAG123X\x03"
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = MockSerial(data)
    callback = mocker.Mock()
    reader.callback = callback

    # Mock time.sleep to avoid waiting
    mocker.patch("time.sleep")

    reader.poll()

    callback.assert_called_once_with("test", "TAG123")
    assert reader.serial_conn.rts is False  # Should have been set to True then False
