import pytest
import numpy as np
import time
from hardware_agent.camera import USBCamera


def test_camera_connect_success(mocker):
    mock_cap = mocker.Mock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 0.0
    mocker.patch("cv2.VideoCapture", return_value=mock_cap)

    camera = USBCamera("test", device=0)
    assert camera.connect() is True
    assert camera.is_connected() is True


def test_camera_connect_fail(mocker):
    mock_cap = mocker.Mock()
    mock_cap.isOpened.return_value = False
    mocker.patch("cv2.VideoCapture", return_value=mock_cap)

    camera = USBCamera("test", device=0)
    assert camera.connect() is False
    assert camera.is_connected() is False


def test_camera_reader_thread(mocker):
    mock_cap = mocker.Mock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 0.0
    # Return (True, frame) many times
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, frame)
    mocker.patch("cv2.VideoCapture", return_value=mock_cap)

    camera = USBCamera("test", device=0)
    camera.connect()

    # Start reader thread manually to control it
    camera.running = True
    camera.on_connect()

    # Wait for frame to be read
    # We use a small sleep since it's a separate thread
    start_time = time.time()
    while camera.read_frame() is None and time.time() - start_time < 2:
        time.sleep(0.1)

    assert camera.read_frame() is not None
    assert np.array_equal(camera.read_frame(), frame)

    camera.running = False
    camera.disconnect()


def test_camera_poll_timeout(mocker):
    mock_cap = mocker.Mock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 0.0
    mock_cap.read.return_value = (False, None)
    mocker.patch("cv2.VideoCapture", return_value=mock_cap)

    camera = USBCamera("test", device=0)
    camera.connect()
    camera.running = True

    # Patch time.perf_counter to simulate timeout
    mocker.patch("time.perf_counter", side_effect=[0, 6])

    with pytest.raises(Exception, match="Timed out waiting for first frame"):
        camera.poll()


def test_camera_poll_success(mocker):
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    camera = USBCamera("test", device=0)
    camera.running = True
    camera._latest_frame = frame
    callback = mocker.Mock()
    camera.callback = callback

    # Mock sleep to avoid waiting
    mocker.patch("time.sleep")

    camera.poll()
    callback.assert_called_once_with("test", frame)


def test_camera_reconnect_does_not_leak_reader_thread(mocker):
    """Reader thread is tracked and joined on disconnect so reconnect
    cycles don't accumulate a growing pile of threads.

    Regression for the bug noted in the tech-debt review: each
    reconnect spawned a new reader thread with no tracking of the old
    one. Over hours of operation on a Pi with flaky USB this would
    leak hundreds of threads.
    """
    mock_cap = mocker.Mock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 0.0
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, frame)
    mocker.patch("cv2.VideoCapture", return_value=mock_cap)

    camera = USBCamera("test", device=0)
    camera.running = True

    reader_threads = []
    # Go through several connect/disconnect cycles.
    for _ in range(5):
        camera.connect()
        camera.on_connect()
        # Let the reader populate a frame.
        start = time.time()
        while camera.read_frame() is None and time.time() - start < 1.0:
            time.sleep(0.02)
        reader_threads.append(camera._reader_thread)
        camera.disconnect()

    # Each cycle must have stored a distinct reader-thread handle,
    # and every one of those threads must have been joined.
    assert len(reader_threads) == 5
    assert all(t is not None for t in reader_threads)
    for t in reader_threads:
        assert not t.is_alive(), (
            f"Reader thread {t} was not joined on disconnect — leak!"
        )
    # All handles must be distinct — we spawned a fresh reader per cycle.
    assert len(set(id(t) for t in reader_threads)) == 5


def test_disconnect_joins_reader_thread(mocker):
    """disconnect() must signal the reader thread to stop and join it
    before releasing the capture device. Without this the reader could
    still be inside cap.read() when cap.release() runs — undefined
    behaviour in OpenCV."""
    mock_cap = mocker.Mock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.return_value = 0.0
    mock_cap.read.return_value = (True, np.zeros((10, 10, 3), dtype=np.uint8))
    mocker.patch("cv2.VideoCapture", return_value=mock_cap)

    camera = USBCamera("test", device=0)
    camera.running = True
    camera.connect()
    camera.on_connect()

    reader = camera._reader_thread
    assert reader is not None and reader.is_alive()

    camera.disconnect()

    # Reader thread must be joined (not alive) after disconnect returns,
    # and only then should cap.release have been called.
    assert not reader.is_alive()
    mock_cap.release.assert_called_once()
    # disconnect() must nil the handle so next connect spawns fresh.
    assert camera._reader_thread is None
    assert camera.cap is None
