import pytest
import time
from hardware_agent.base import BaseSensor


class MockSensor(BaseSensor):
    def __init__(self, name):
        super().__init__(name)
        self.connected = False
        self.should_connect = False
        self.poll_count = 0
        self.connect_calls = 0

    def connect(self):
        self.connect_calls += 1
        if self.should_connect:
            self.connected = True
            return True
        return False

    def disconnect(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    def poll(self):
        self.poll_count += 1
        if self.poll_count > 1000:  # increased for fast loops
            self.running = False


def wait_for(condition, timeout=10.0):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition():
            return
        time.sleep(0.1)
    pytest.fail("Timeout waiting for condition")


def test_base_sensor_reconnection_loop(mocker):
    # Mock time.sleep in the base module to speed up the test
    mocker.patch("hardware_agent.base.time.sleep")
    sensor = MockSensor("test")
    status_mock = mocker.Mock()

    # Start with disconnected
    sensor.should_connect = False

    # Start the sensor
    sensor.start(callback=mocker.Mock(), status_callback=status_mock)

    # Wait for first connection attempt
    wait_for(lambda: sensor.connect_calls >= 1)
    status_mock.assert_any_call("test", False, "Disconnected")

    # Now allow connection
    sensor.should_connect = True

    # Wait for connection status success
    wait_for(
        lambda: any(
            call == mocker.call("test", True) for call in status_mock.call_args_list
        )
    )

    # Should be polling
    wait_for(lambda: sensor.poll_count > 0)

    sensor.stop()


def test_base_sensor_error_handling(mocker):
    # Here we don't have a 5s sleep in the success path, so it should be fast
    sensor = MockSensor("test")
    sensor.connected = True
    status_mock = mocker.Mock()

    def fail_poll():
        raise RuntimeError("boom")

    mocker.patch.object(sensor, "poll", side_effect=fail_poll)

    sensor.start(callback=mocker.Mock(), status_callback=status_mock)

    # Wait for error message
    wait_for(lambda: any("boom" in str(args) for args in status_mock.call_args_list))

    # It should have disconnected
    wait_for(lambda: sensor.connected is False)

    sensor.stop()
