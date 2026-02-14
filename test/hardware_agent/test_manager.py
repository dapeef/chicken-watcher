import pytest
from hardware_agent.manager import HardwareManager


@pytest.mark.django_db
class TestHardwareManager:
    def test_add_rfid_reader_no_port(self, mocker):
        manager = HardwareManager()
        # Mock report_status to verify it's called
        mock_report = mocker.patch("hardware_agent.manager.report_status")

        manager.add_rfid_reader("TestReader", "")

        mock_report.assert_called_once_with(
            "rfid_TestReader", False, "No port configured"
        )
        assert len(manager.sensors) == 0

    def test_add_rfid_reader_success(self, mocker):
        mock_reader = mocker.patch("hardware_agent.manager.RFIDReader")
        manager = HardwareManager()

        manager.add_rfid_reader("TestReader", "/dev/ttyUSB0")

        assert len(manager.sensors) == 1
        mock_reader.assert_called_once_with("TestReader", "/dev/ttyUSB0")
        mock_reader.return_value.start.assert_called_once()

    def test_add_camera_no_device(self, mocker):
        manager = HardwareManager()
        mock_report = mocker.patch("hardware_agent.manager.report_status")

        manager.add_camera("TestCam", "")

        mock_report.assert_called_once_with(
            "camera_TestCam", False, "No device configured"
        )
        assert len(manager.sensors) == 0

    def test_add_camera_success(self, mocker):
        mock_cam = mocker.patch("hardware_agent.manager.USBCamera")
        manager = HardwareManager()

        manager.add_camera("TestCam", "/dev/video0")

        assert len(manager.sensors) == 1
        mock_cam.assert_called_once_with("TestCam", device="/dev/video0", fps=1)
        mock_cam.return_value.start.assert_called_once()

    def test_add_beam_sensor_invalid_gpio(self, mocker):
        manager = HardwareManager()
        mock_report = mocker.patch("hardware_agent.manager.report_status")

        manager.add_beam_sensor("TestBeam", "invalid", pin_factory=mocker.Mock())

        mock_report.assert_called_once_with(
            "beam_TestBeam", False, "Invalid GPIO: invalid"
        )
        assert len(manager.sensors) == 0

    def test_add_beam_sensor_success(self, mocker):
        mock_beam = mocker.patch("hardware_agent.manager.BeamSensor")
        manager = HardwareManager()
        mock_factory = mocker.Mock()

        manager.add_beam_sensor("TestBeam", "17", pin_factory=mock_factory)

        assert len(manager.sensors) == 1
        mock_beam.assert_called_once_with("TestBeam", 17, pin_factory=mock_factory)
        mock_beam.return_value.start.assert_called_once()
