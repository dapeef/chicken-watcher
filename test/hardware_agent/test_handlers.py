import pytest
import numpy as np
from hardware_agent.handlers import handle_tag_read, handle_beam_break, save_frame_to_db
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

    def test_save_frame_to_db(self, mocker):
        # Create a dummy frame (numpy array)
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        HardwareSensor.objects.create(name="camera_Cam1")
        
        save_frame_to_db("Cam1", frame)
        
        image_record = NestingBoxImage.objects.first()
        assert image_record is not None
        # The filename in image_record.image.name includes the upload_to path
        assert "Cam1_" in image_record.image.name
