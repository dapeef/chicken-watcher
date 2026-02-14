import pytest
import numpy as np
from hardware_agent.handlers import (
    handle_tag_read,
    handle_beam_break,
    save_frame_to_db,
    report_status,
    report_event,
    save_frame_to_file,
)
import pathlib
from web_app.models import NestingBoxPresence, Egg, NestingBoxImage, HardwareSensor
from test.web_app.factories import ChickenFactory, NestingBoxFactory

@pytest.mark.django_db
class TestHardwareHandlers:
    def test_handle_tag_read(self, mocker):
        chicken = ChickenFactory(tag_string="12345")
        box = NestingBoxFactory(name="Box1")
        HardwareSensor.objects.create(name="rfid_Box1")
        
        handle_tag_read("Box1", "12345")
        
        presence = NestingBoxPresence.objects.filter(chicken=chicken, nesting_box=box).first()
        assert presence is not None
        
        # Check if sensor status was updated
        sensor = HardwareSensor.objects.get(name="rfid_Box1")
        assert sensor.is_connected is True

    def test_handle_tag_read_unknown_chicken(self, mocker):
        box = NestingBoxFactory(name="Box1")
        # Should not raise exception, just print error
        handle_tag_read("Box1", "unknown")
        assert NestingBoxPresence.objects.count() == 0

    def test_handle_tag_read_unknown_box(self, mocker):
        ChickenFactory(tag_string="12345")
        # Should not raise exception, just print error
        handle_tag_read("UnknownBox", "12345")
        assert NestingBoxPresence.objects.count() == 0

    def test_handle_beam_break(self, mocker):
        chicken = ChickenFactory()
        box = NestingBoxFactory(name="Box1")
        HardwareSensor.objects.create(name="beam_Box1")
        # Create a presence record
        NestingBoxPresence.objects.create(chicken=chicken, nesting_box=box)
        
        handle_beam_break("Box1")
        
        egg = Egg.objects.filter(chicken=chicken, nesting_box=box).first()
        assert egg is not None
        
        # Check sensor status
        sensor = HardwareSensor.objects.get(name="beam_Box1")
        assert sensor.is_connected is True

    def test_handle_beam_break_no_presence(self, mocker):
        box = NestingBoxFactory(name="Box1")
        # Should not create an egg
        handle_beam_break("Box1")
        assert Egg.objects.count() == 0

    def test_save_frame_to_db(self, mocker):
        # Create a dummy frame (numpy array)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        HardwareSensor.objects.create(name="camera_Cam1")
        
        save_frame_to_db("Cam1", frame)
        
        image_record = NestingBoxImage.objects.first()
        assert image_record is not None
        # The filename in image_record.image.name includes the upload_to path
        assert "Cam1_" in image_record.image.name

    def test_save_frame_to_db_encode_fail(self, mocker):
        mocker.patch("cv2.imencode", return_value=(False, None))
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        
        with pytest.raises(RuntimeError, match="Could not encode frame"):
            save_frame_to_db("Cam1", frame)

    def test_report_status(self):
        report_status("test_sensor", True, "All good")
        sensor = HardwareSensor.objects.get(name="test_sensor")
        assert sensor.is_connected is True
        assert sensor.status_message == "All good"

    def test_report_event(self):
        HardwareSensor.objects.create(name="test_sensor", is_connected=False)
        report_event("test_sensor")
        sensor = HardwareSensor.objects.get(name="test_sensor")
        assert sensor.is_connected is True
        assert sensor.last_event_at is not None

    def test_save_frame_to_file(self, tmp_path, mocker):
        # Mock pathlib.Path("frames") to use tmp_path
        mocker.patch("hardware_agent.handlers.pathlib.Path", return_value=tmp_path)

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        save_frame_to_file("CamTest", frame)

        # Check if file was created in tmp_path
        files = list(tmp_path.glob("CamTest_*.jpg"))
        assert len(files) == 1
