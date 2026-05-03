import pytest
import serial

from hardware_agent.rfid_reader import RFIDReader


class MockSerial:
    def __init__(self, data_to_read=None):
        self.data_to_read = data_to_read or b""
        self.is_open = True
        self._rts = False
        self._dtr = False
        self.close_called = False
        self.reset_input_buffer_calls = 0
        # Set to an exception instance to make reset_input_buffer() raise.
        self.reset_input_buffer_failure: Exception | None = None
        # Test hook: a list of exceptions to raise on each successive
        # rts/dtr setattr. ``None`` entries mean "this assignment
        # succeeds". Empty list means assignments always succeed.
        self.modem_failures: list[Exception | None] = []
        self.modem_writes: list[tuple[str, bool]] = []

    def _maybe_fail(self) -> None:
        if not self.modem_failures:
            return
        exc = self.modem_failures.pop(0)
        if exc is not None:
            raise exc

    @property
    def rts(self) -> bool:
        return self._rts

    @rts.setter
    def rts(self, value: bool) -> None:
        self._maybe_fail()
        self._rts = value
        self.modem_writes.append(("rts", value))

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        self._maybe_fail()
        self._dtr = value
        self.modem_writes.append(("dtr", value))

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

    def reset_input_buffer(self):
        self.reset_input_buffer_calls += 1
        self.data_to_read = b""
        if self.reset_input_buffer_failure is not None:
            raise self.reset_input_buffer_failure

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


@pytest.mark.parametrize("reset_line", ["dtr", "rts"])
def test_rfid_reader_poll(mocker, reset_line):
    data = b"\x02TAG123X\x03"
    reader = RFIDReader("test", "/dev/ttyUSB0", reset_line=reset_line)
    reader.serial_conn = MockSerial(data)
    callback = mocker.Mock()
    reader.callback = callback

    mocker.patch("time.sleep")

    reader.poll()

    callback.assert_called_once_with("test", "TAG123")
    # Only the configured reset line should have been pulsed; the other
    # must remain untouched (no unnecessary USB control transfers).
    other_line = "rts" if reset_line == "dtr" else "dtr"
    assert getattr(reader.serial_conn, reset_line) is False
    assert not any(name == other_line for name, _ in reader.serial_conn.modem_writes)
    # Input buffer flushed after the pulse.
    assert reader.serial_conn.reset_input_buffer_calls == 1


def test_rfid_reader_invalid_reset_line():
    with pytest.raises(ValueError, match="reset_line"):
        RFIDReader("test", "/dev/ttyUSB0", reset_line="cts")


@pytest.mark.parametrize("reset_line", ["dtr", "rts"])
def test_on_connect_idles_reset_line_low(mocker, reset_line):
    reader = RFIDReader("test", "/dev/ttyUSB0", reset_line=reset_line)
    reader.serial_conn = MockSerial()
    # Pre-set both high so we can confirm only the configured line is driven.
    reader.serial_conn._rts = True
    reader.serial_conn._dtr = True
    mocker.patch("time.sleep")

    reader.on_connect()

    # Configured line driven low.
    assert getattr(reader.serial_conn, reset_line) is False
    # Other line not touched.
    other_line = "rts" if reset_line == "dtr" else "dtr"
    assert not any(name == other_line for name, _ in reader.serial_conn.modem_writes)


def test_set_modem_line_retries_on_transient_eproto(mocker):
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = MockSerial()
    # First attempt fails with EPROTO, second attempt succeeds.
    reader.serial_conn.modem_failures = [OSError(71, "Protocol error")]
    sleep_mock = mocker.patch("time.sleep")

    reader._set_modem_line("rts", True)

    # Eventually succeeded.
    assert reader.serial_conn.rts is True
    # Backoff slept exactly once between the failed attempt and the retry.
    sleep_mock.assert_called_once_with(reader._MODEM_RETRY_BACKOFF)


def test_set_modem_line_raises_after_persistent_failure(mocker):
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = MockSerial()
    # All retry attempts fail.
    reader.serial_conn.modem_failures = [
        OSError(71, "Protocol error") for _ in range(reader._MODEM_RETRY_ATTEMPTS)
    ]
    mocker.patch("time.sleep")

    try:
        reader._set_modem_line("rts", True)
    except OSError as e:
        assert e.errno == 71
    else:
        raise AssertionError("Expected OSError to be raised after exhausting retries")


def test_on_connect_propagates_persistent_eproto(mocker):
    """A persistent EPROTO must escape on_connect so the loop disconnects
    and reconnects rather than continuing on a bad serial port."""
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = MockSerial()
    reader.serial_conn.modem_failures = [
        OSError(71, "Protocol error") for _ in range(reader._MODEM_RETRY_ATTEMPTS)
    ]
    mocker.patch("time.sleep")

    try:
        reader.on_connect()
    except OSError as e:
        assert e.errno == 71
    else:
        raise AssertionError("Expected OSError to propagate out of on_connect")


def test_recv_frame_raises_on_corrupt_stream():
    """If the STX hunt consumes more than _MAX_SYNC_BYTES without finding
    a frame start, the stream is considered corrupt and RuntimeError is
    raised so BaseSensor can disconnect and reconnect."""
    # Fill the buffer with more garbage bytes than the limit, none of which
    # is STX (0x02).
    garbage = bytes([0xFF] * (RFIDReader._MAX_SYNC_BYTES + 1))
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = MockSerial(garbage)

    with pytest.raises(RuntimeError, match="stream corrupt"):
        reader.recv_frame()


def test_recv_frame_tolerates_garbage_before_stx():
    """Garbage bytes before STX within the limit should be silently
    discarded and the valid frame still returned."""
    # A few garbage bytes, then a valid frame.
    data = b"\xff\xfe\xfd\x02TAG123X\x03"
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = MockSerial(data)

    frame = reader.recv_frame()
    assert frame == b"TAG123X"


def test_poll_reset_line_deasserted_if_flush_fails(mocker):
    """If reset_input_buffer() raises, the reset line must already have
    been driven low (via try/finally) before the exception propagates.
    Without this guarantee the reader is held in reset across the full
    reconnect backoff wait."""
    data = b"\x02TAG123X\x03"
    reader = RFIDReader("test", "/dev/ttyUSB0", reset_line="dtr")
    reader.serial_conn = MockSerial(data)
    reader.serial_conn.reset_input_buffer_failure = OSError("flush failed")
    reader.callback = mocker.Mock()
    mocker.patch("time.sleep")

    with pytest.raises(OSError, match="flush failed"):
        reader.poll()

    # The line must be low despite the exception — reader is not stuck in reset.
    assert reader.serial_conn.dtr is False


def test_poll_reset_input_buffer_failure_propagates(mocker):
    """A reset_input_buffer() failure must escape poll() so BaseSensor
    triggers a disconnect/reconnect rather than continuing with a dirty
    buffer that would corrupt subsequent reads."""
    data = b"\x02TAG123X\x03"
    reader = RFIDReader("test", "/dev/ttyUSB0")
    reader.serial_conn = MockSerial(data)
    reader.serial_conn.reset_input_buffer_failure = OSError(71, "Protocol error")
    reader.callback = mocker.Mock()
    mocker.patch("time.sleep")

    with pytest.raises(OSError):
        reader.poll()


def test_poll_no_reset_pulse_when_reset_line_none(mocker):
    """When reset_line=None, poll() must fire the callback but make no
    modem-control writes and no reset_input_buffer call — the line stays
    low as set by on_connect."""
    data = b"\x02TAG123X\x03"
    reader = RFIDReader("test", "/dev/ttyUSB0", reset_line=None)
    reader.serial_conn = MockSerial(data)
    reader.callback = mocker.Mock()
    mocker.patch("time.sleep")

    reader.poll()

    reader.callback.assert_called_once_with("test", "TAG123")
    assert reader.serial_conn.modem_writes == []
    assert reader.serial_conn.reset_input_buffer_calls == 0


def test_on_connect_pins_both_lines_low_when_reset_line_none(mocker):
    """When reset_line=None both RTS and DTR must be driven low on connect.
    The kernel/pyserial does not guarantee an initial state, so whichever
    line is wired to RST on the adapter must be explicitly held low to
    prevent the reader being stuck in reset."""
    reader = RFIDReader("test", "/dev/ttyUSB0", reset_line=None)
    reader.serial_conn = MockSerial()
    reader.serial_conn._dtr = True
    reader.serial_conn._rts = True

    reader.on_connect()

    assert reader.serial_conn.rts is False
    assert reader.serial_conn.dtr is False
