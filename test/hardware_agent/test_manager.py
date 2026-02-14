import pytest
from hardware_agent.manager import HardwareManager
from web_app.models import HardwareSensor

@pytest.mark.django_db
class TestHardwareManager:
    def test_add_rfid_reader_no_port(self, mocker):
        manager = HardwareManager()
        # Mock report_status to verify it's called
        mock_report = mocker.patch("hardware_agent.manager.report_status")
        
        manager.add_rfid_reader("TestReader", "")
        
        mock_report.assert_called_once_with("rfid_TestReader", False, "No port configured")
        assert len(manager.sensors) == 0

    def test_add_camera_no_device(self, mocker):
        manager = HardwareManager()
        mock_report = mocker.patch("hardware_agent.manager.report_status")
        
        manager.add_camera("TestCam", "")
        
        mock_report.assert_called_once_with("camera_TestCam", False, "No device configured")
        assert len(manager.sensors) == 0

    def test_add_beam_sensor_invalid_gpio(self, mocker):
        manager = HardwareManager()
        mock_report = mocker.patch("hardware_agent.manager.report_status")
        
        manager.add_beam_sensor("TestBeam", "invalid", pin_factory=mocker.Mock())
        
        mock_report.assert_called_once_with("beam_TestBeam", False, "Invalid GPIO: invalid")
        assert len(manager.sensors) == 0
