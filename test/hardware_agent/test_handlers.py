import logging

import pytest
import numpy as np
from hardware_agent.handlers import (
    handle_tag_read,
    handle_beam_break,
    save_frame_to_db,
    report_status,
    report_event,
    save_frame_to_file,
    _nesting_box_name_for_sensor,
)
from web_app.models import (
    NestingBoxPresence,
    Egg,
    NestingBoxImage,
    HardwareSensor,
    NestingBoxPresencePeriod,
)
from test.web_app.factories import TagFactory, ChickenFactory, NestingBoxFactory


@pytest.mark.django_db
class TestHardwareHandlers:
    def test_handle_tag_read(self, mocker):
        chicken = ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        box = NestingBoxFactory(name="Box1")
        HardwareSensor.objects.create(name="rfid_Box1")

        handle_tag_read("Box1", "12345")

        presence = NestingBoxPresence.objects.filter(
            chicken=chicken, nesting_box=box
        ).first()
        assert presence is not None
        assert presence.presence_period is not None
        assert presence.presence_period.chicken == chicken
        assert presence.presence_period.nesting_box == box

        # Check if sensor status was updated
        sensor = HardwareSensor.objects.get(name="rfid_Box1")
        assert sensor.is_connected is True

    def test_handle_tag_read_extend_period(self, mocker):
        from datetime import timedelta
        from django.utils import timezone

        chicken = ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        box = NestingBoxFactory(name="Box1")
        HardwareSensor.objects.create(name="rfid_Box1")

        # First read
        handle_tag_read("Box1", "12345")
        period1 = NestingBoxPresencePeriod.objects.get()
        assert period1.started_at == period1.ended_at

        # Second read 30 seconds later (within 60s timeout)
        future_time = timezone.now() + timedelta(seconds=30)
        mocker.patch("django.utils.timezone.now", return_value=future_time)

        handle_tag_read("Box1", "12345")

        assert NestingBoxPresencePeriod.objects.count() == 1
        period = NestingBoxPresencePeriod.objects.get()
        assert period.ended_at == future_time
        assert NestingBoxPresence.objects.count() == 2
        for presence in NestingBoxPresence.objects.all():
            assert presence.presence_period == period

    def test_handle_tag_read_new_period_after_timeout(self, mocker):
        from datetime import timedelta
        from django.utils import timezone

        chicken = ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        box = NestingBoxFactory(name="Box1")
        HardwareSensor.objects.create(name="rfid_Box1")

        # First read
        handle_tag_read("Box1", "12345")

        # Second read 90 seconds later (outside 60s timeout)
        future_time = timezone.now() + timedelta(seconds=90)
        mocker.patch("django.utils.timezone.now", return_value=future_time)

        handle_tag_read("Box1", "12345")

        assert NestingBoxPresencePeriod.objects.count() == 2
        assert NestingBoxPresence.objects.count() == 2

        presences = list(NestingBoxPresence.objects.order_by("present_at"))
        assert presences[0].presence_period != presences[1].presence_period

    def test_handle_tag_read_do_not_extend_if_seen_elsewhere(self, mocker):
        from datetime import timedelta
        from django.utils import timezone

        chicken = ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        box1 = NestingBoxFactory(name="Box1")
        box2 = NestingBoxFactory(name="Box2")
        HardwareSensor.objects.create(name="rfid_Box1")
        HardwareSensor.objects.create(name="rfid_Box2")

        t0 = timezone.now()

        # 1. Spotted in Box 1
        mocker.patch("django.utils.timezone.now", return_value=t0)
        handle_tag_read("Box1", "12345")

        # 2. Spotted in Box 2 after 10 seconds
        t1 = t0 + timedelta(seconds=10)
        mocker.patch("django.utils.timezone.now", return_value=t1)
        handle_tag_read("Box2", "12345")

        # 3. Spotted in Box 1 again after another 10 seconds (total 20s from first Box 1 read)
        t2 = t1 + timedelta(seconds=10)
        mocker.patch("django.utils.timezone.now", return_value=t2)
        handle_tag_read("Box1", "12345")

        periods = NestingBoxPresencePeriod.objects.filter(nesting_box=box1).order_by(
            "started_at"
        )
        assert periods.count() == 2
        assert periods[0].ended_at == t0
        assert periods[1].started_at == t2

    def test_handle_tag_read_unknown_rfid(self, mocker, caplog):
        NestingBoxFactory(name="Box1")
        with caplog.at_level(logging.ERROR, logger="hardware_agent.handlers"):
            handle_tag_read("Box1", "unknown")
        assert NestingBoxPresence.objects.count() == 0
        assert any(
            "No tag found matching rfid string" in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )

    def test_handle_tag_read_no_live_chicken_for_tag(self, mocker, caplog):
        # Tag exists but has no live chicken assigned (e.g. previous chicken has died)
        TagFactory(rfid_string="12345", number=1)
        NestingBoxFactory(name="Box1")
        with caplog.at_level(logging.ERROR, logger="hardware_agent.handlers"):
            handle_tag_read("Box1", "12345")
        assert NestingBoxPresence.objects.count() == 0
        assert any(
            "No live chicken found assigned to tag" in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )

    def test_handle_tag_read_unknown_box(self, mocker, caplog):
        ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        with caplog.at_level(logging.ERROR, logger="hardware_agent.handlers"):
            handle_tag_read("UnknownBox", "12345")
        assert NestingBoxPresence.objects.count() == 0
        assert any(
            "No matching nesting box found matching name" in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )

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

    def test_handle_beam_break_no_presence(self, mocker, caplog):
        NestingBoxFactory(name="Box1")
        with caplog.at_level(logging.WARNING, logger="hardware_agent.handlers"):
            handle_beam_break("Box1")
        assert Egg.objects.count() == 0
        assert any(
            "No NestingBoxPresence found for box" in r.message
            and r.levelno == logging.WARNING
            for r in caplog.records
        )

    def test_handle_beam_break_unknown_box(self, caplog):
        with caplog.at_level(logging.ERROR, logger="hardware_agent.handlers"):
            handle_beam_break("UnknownBox")
        assert Egg.objects.count() == 0
        assert any(
            "No matching nesting box found matching name" in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )

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

    def test_save_frame_to_db_logs_debug(self, caplog):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with caplog.at_level(logging.DEBUG, logger="hardware_agent.handlers"):
            save_frame_to_db("Cam1", frame)
        assert any(
            "frame saved to db as" in r.message and r.levelno == logging.DEBUG
            for r in caplog.records
        )

    def test_report_status_logs_error_on_db_failure(self, mocker, caplog):
        mocker.patch(
            "hardware_agent.handlers.HardwareSensor.objects.update_or_create",
            side_effect=Exception("DB unavailable"),
        )
        with caplog.at_level(logging.ERROR, logger="hardware_agent.handlers"):
            report_status("test_sensor", True)
        assert any(
            "Error reporting status for test_sensor" in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )

    def test_report_event_logs_error_on_db_failure(self, mocker, caplog):
        mocker.patch(
            "hardware_agent.handlers.HardwareSensor.objects.filter",
            side_effect=Exception("DB unavailable"),
        )
        with caplog.at_level(logging.ERROR, logger="hardware_agent.handlers"):
            report_event("test_sensor")
        assert any(
            "Error reporting event for test_sensor" in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )


class TestNestingBoxNameForSensor:
    """Unit tests for _nesting_box_name_for_sensor()."""

    def test_plain_name_returned_unchanged(self):
        assert _nesting_box_name_for_sensor("left") == "left"
        assert _nesting_box_name_for_sensor("right") == "right"

    def test_single_digit_suffix_stripped(self):
        assert _nesting_box_name_for_sensor("left_1") == "left"
        assert _nesting_box_name_for_sensor("left_2") == "left"
        assert _nesting_box_name_for_sensor("left_3") == "left"
        assert _nesting_box_name_for_sensor("left_4") == "left"
        assert _nesting_box_name_for_sensor("right_1") == "right"
        assert _nesting_box_name_for_sensor("right_4") == "right"

    def test_multi_digit_suffix_stripped(self):
        assert _nesting_box_name_for_sensor("left_12") == "left"
        assert _nesting_box_name_for_sensor("right_99") == "right"

    def test_letter_suffix_not_stripped(self):
        # Letters are not digit suffixes in the new scheme
        assert _nesting_box_name_for_sensor("left_a") == "left_a"
        assert _nesting_box_name_for_sensor("left_b") == "left_b"

    def test_arbitrary_box_names(self):
        assert _nesting_box_name_for_sensor("Box1") == "Box1"
        assert _nesting_box_name_for_sensor("UnknownBox") == "UnknownBox"


@pytest.mark.django_db
class TestMultiSensorTagRead:
    """Tests for RFID reads from multiple sensors in the same nesting box."""

    def test_sensor_id_recorded_on_presence(self):
        """The sensor name is stored in sensor_id on NestingBoxPresence."""
        chicken = ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        NestingBoxFactory(name="left")
        HardwareSensor.objects.create(name="rfid_left_1")

        handle_tag_read("left_1", "12345")

        presence = NestingBoxPresence.objects.get(chicken=chicken)
        assert presence.sensor_id == "left_1"

    def test_nesting_box_resolved_from_sensor_suffix(self):
        """Sensor 'left_1' reads into the 'left' nesting box."""
        chicken = ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        box = NestingBoxFactory(name="left")
        HardwareSensor.objects.create(name="rfid_left_1")

        handle_tag_read("left_1", "12345")

        presence = NestingBoxPresence.objects.get(chicken=chicken)
        assert presence.nesting_box == box

    def test_four_sensors_in_same_box_all_create_presences(self):
        """Reads from left_1 through left_4 all create presences linked to the left box."""
        chicken = ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        box = NestingBoxFactory(name="left")
        for n in range(1, 5):
            HardwareSensor.objects.create(name=f"rfid_left_{n}")

        for n in range(1, 5):
            handle_tag_read(f"left_{n}", "12345")

        presences = NestingBoxPresence.objects.filter(nesting_box=box).order_by(
            "present_at"
        )
        assert presences.count() == 4
        assert [p.sensor_id for p in presences] == [
            "left_1",
            "left_2",
            "left_3",
            "left_4",
        ]
        assert all(p.nesting_box == box for p in presences)

    def test_multiple_sensors_in_same_box_share_presence_period(self):
        """Back-to-back reads from left_1 and left_2 extend the same period."""
        chicken = ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        NestingBoxFactory(name="left")
        HardwareSensor.objects.create(name="rfid_left_1")
        HardwareSensor.objects.create(name="rfid_left_2")

        handle_tag_read("left_1", "12345")
        handle_tag_read("left_2", "12345")

        from web_app.models import NestingBoxPresencePeriod

        # Both presences should belong to the same period because both sensors
        # are in the same box and reads happen within the 60-second window.
        assert NestingBoxPresencePeriod.objects.count() == 1
        assert NestingBoxPresence.objects.count() == 2

    def test_unknown_box_error_uses_derived_name(self, caplog):
        """When the nesting box is not found, the error log uses the derived box name."""
        ChickenFactory(tag=TagFactory(rfid_string="12345", number=1))
        # No nesting box created — lookup should fail for "left" (derived from "left_1")
        with caplog.at_level(logging.ERROR, logger="hardware_agent.handlers"):
            handle_tag_read("left_1", "12345")
        assert NestingBoxPresence.objects.count() == 0
        assert any(
            "No matching nesting box found matching name: left" in r.message
            and r.levelno == logging.ERROR
            for r in caplog.records
        )
