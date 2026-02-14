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
