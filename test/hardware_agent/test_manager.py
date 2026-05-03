import logging

import pytest

from hardware_agent.manager import HardwareManager


@pytest.mark.django_db
class TestHardwareManager:
    def test_add_rfid_reader_no_port(self, mocker, caplog):
        manager = HardwareManager()
        # Mock report_status to verify it's called
        mock_report = mocker.patch("hardware_agent.manager.report_status")

        with caplog.at_level(logging.WARNING, logger="hardware_agent.manager"):
            manager.add_rfid_reader("TestReader", "")

        mock_report.assert_called_once_with("rfid_TestReader", False, "No port configured")
        assert len(manager.sensors) == 0
        assert any(
            "Skipping RFID reader" in r.message and "TestReader" in r.message
            for r in caplog.records
        )

    def test_add_rfid_reader_success(self, mocker):
        mock_reader = mocker.patch("hardware_agent.manager.RFIDReader")
        manager = HardwareManager()

        manager.add_rfid_reader("TestReader", "/dev/ttyUSB0")

        assert len(manager.sensors) == 1
        mock_reader.assert_called_once_with("TestReader", "/dev/ttyUSB0", reset_line="dtr")
        mock_reader.return_value.start.assert_called_once()

    def test_add_camera_no_device(self, mocker, caplog):
        manager = HardwareManager()
        mock_report = mocker.patch("hardware_agent.manager.report_status")

        with caplog.at_level(logging.WARNING, logger="hardware_agent.manager"):
            manager.add_camera("TestCam", "")

        mock_report.assert_called_once_with("camera_TestCam", False, "No device configured")
        assert len(manager.sensors) == 0
        assert any(
            "Skipping camera" in r.message and "TestCam" in r.message for r in caplog.records
        )

    def test_add_camera_success(self, mocker):
        mock_cam = mocker.patch("hardware_agent.manager.USBCamera")
        manager = HardwareManager()

        manager.add_camera("TestCam", "/dev/video0")

        assert len(manager.sensors) == 1
        mock_cam.assert_called_once_with("TestCam", device="/dev/video0", fps=1)
        mock_cam.return_value.start.assert_called_once()

    def test_add_beam_sensor_invalid_gpio(self, mocker, caplog):
        manager = HardwareManager()
        mock_report = mocker.patch("hardware_agent.manager.report_status")

        with caplog.at_level(logging.WARNING, logger="hardware_agent.manager"):
            manager.add_beam_sensor("TestBeam", "invalid", pin_factory=mocker.Mock())

        mock_report.assert_called_once_with("beam_TestBeam", False, "Invalid GPIO: invalid")
        assert len(manager.sensors) == 0
        assert any(
            "Skipping beam sensor" in r.message and "TestBeam" in r.message for r in caplog.records
        )

    def test_add_beam_sensor_no_gpio(self, mocker, caplog):
        manager = HardwareManager()
        mock_report = mocker.patch("hardware_agent.manager.report_status")

        with caplog.at_level(logging.WARNING, logger="hardware_agent.manager"):
            manager.add_beam_sensor("TestBeam", "", pin_factory=mocker.Mock())

        mock_report.assert_called_once_with("beam_TestBeam", False, "No GPIO configured")
        assert len(manager.sensors) == 0
        assert any(
            "Skipping beam sensor" in r.message and "TestBeam" in r.message for r in caplog.records
        )

    def test_add_beam_sensor_no_pin_factory(self, mocker, caplog):
        manager = HardwareManager()
        mock_report = mocker.patch("hardware_agent.manager.report_status")

        with caplog.at_level(logging.WARNING, logger="hardware_agent.manager"):
            manager.add_beam_sensor("TestBeam", "17", pin_factory=None)

        mock_report.assert_called_once_with("beam_TestBeam", False, "LGPIO not available")
        assert len(manager.sensors) == 0
        assert any(
            "Skipping beam sensor" in r.message and "TestBeam" in r.message for r in caplog.records
        )

    def test_add_beam_sensor_success(self, mocker):
        mock_beam = mocker.patch("hardware_agent.manager.BeamSensor")
        manager = HardwareManager()
        mock_factory = mocker.Mock()

        manager.add_beam_sensor("TestBeam", "17", pin_factory=mock_factory)

        assert len(manager.sensors) == 1
        mock_beam.assert_called_once_with("TestBeam", 17, pin_factory=mock_factory)
        mock_beam.return_value.start.assert_called_once()

    def test_stop_all_stops_every_sensor(self, mocker):
        """stop_all() iterates over registered sensors and calls stop()
        on each so hardware handles are released on SIGTERM/SIGINT."""
        manager = HardwareManager()
        sensor1 = mocker.Mock(name="sensor1")
        sensor2 = mocker.Mock(name="sensor2")
        sensor3 = mocker.Mock(name="sensor3")
        manager.sensors = [sensor1, sensor2, sensor3]

        manager.stop_all()

        sensor1.stop.assert_called_once()
        sensor2.stop.assert_called_once()
        sensor3.stop.assert_called_once()

    def test_stop_all_continues_when_one_sensor_raises(self, mocker, caplog):
        """A failure in one sensor's stop() must not prevent others from
        being stopped. The goal is best-effort cleanup of all hardware
        handles before process exit."""
        import logging

        manager = HardwareManager()
        sensor1 = mocker.Mock(name="sensor1")
        sensor1.name = "sensor1"
        sensor2_bad = mocker.Mock(name="sensor2_bad")
        sensor2_bad.name = "sensor2_bad"
        sensor2_bad.stop.side_effect = RuntimeError("device stuck")
        sensor3 = mocker.Mock(name="sensor3")
        sensor3.name = "sensor3"
        manager.sensors = [sensor1, sensor2_bad, sensor3]

        with caplog.at_level(logging.ERROR, logger="hardware_agent.manager"):
            manager.stop_all()

        # Every sensor got a stop() call, even though #2 raised.
        sensor1.stop.assert_called_once()
        sensor2_bad.stop.assert_called_once()
        sensor3.stop.assert_called_once()
        # And the failure was logged at ERROR.
        assert any("Error stopping sensor sensor2_bad" in r.message for r in caplog.records)

    def test_stop_all_passes_timeout_to_each_sensor(self, mocker):
        manager = HardwareManager()
        sensor = mocker.Mock()
        manager.sensors = [sensor]

        manager.stop_all(timeout=3.5)

        sensor.stop.assert_called_once_with(timeout=3.5)
