import time

import pytest

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
            self._stop_event.set()


def wait_for(condition, timeout=5.0):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition():
            return
        time.sleep(0.02)
    pytest.fail("Timeout waiting for condition")


@pytest.fixture
def fast_reconnect(mocker):
    """Shrink the reconnect backoff so tests don't pause 5s between
    attempts."""
    mocker.patch("hardware_agent.base.RECONNECT_INTERVAL_SECONDS", 0.01)


def test_base_sensor_reconnection_loop(mocker, fast_reconnect):
    sensor = MockSensor("test")
    status_mock = mocker.Mock()

    sensor.should_connect = False
    sensor.start(callback=mocker.Mock(), status_callback=status_mock)

    # Wait for first failed connect attempt
    wait_for(lambda: sensor.connect_calls >= 1)
    status_mock.assert_any_call("test", False, "Disconnected")

    # Now allow connection
    sensor.should_connect = True

    # Wait for connection status success
    wait_for(lambda: any(call == mocker.call("test", True) for call in status_mock.call_args_list))

    # Should be polling
    wait_for(lambda: sensor.poll_count > 0)

    sensor.stop()


def test_base_sensor_error_handling(mocker, fast_reconnect):
    sensor = MockSensor("test")
    sensor.connected = True
    status_mock = mocker.Mock()

    def fail_poll():
        raise RuntimeError("boom")

    mocker.patch.object(sensor, "poll", side_effect=fail_poll)

    sensor.start(callback=mocker.Mock(), status_callback=status_mock)

    # Wait for error message
    wait_for(lambda: any("boom" in str(args) for args in status_mock.call_args_list))

    # handle_error (default impl) should have disconnected
    wait_for(lambda: sensor.connected is False)

    sensor.stop()


def test_stop_is_idempotent(mocker, fast_reconnect):
    """Calling stop() twice must not raise or leak a thread."""
    sensor = MockSensor("test")
    sensor.should_connect = True
    sensor.start(callback=mocker.Mock())
    wait_for(lambda: sensor.poll_count > 0)
    sensor.stop()
    # Second stop should be a no-op, not an error.
    sensor.stop()


def test_stop_interrupts_reconnect_backoff_fast(mocker):
    """stop() must not block for the full RECONNECT_INTERVAL_SECONDS when
    called during a backoff wait. The stop event wakes the loop early."""
    # Keep the real 5-second default — the point of the test is that
    # stop() doesn't wait that long.
    sensor = MockSensor("test")
    sensor.should_connect = False  # connect() always fails → enters backoff
    sensor.start(callback=mocker.Mock())

    # Let the sensor enter the backoff wait at least once.
    wait_for(lambda: sensor.connect_calls >= 1)

    t0 = time.perf_counter()
    sensor.stop()
    elapsed = time.perf_counter() - t0

    # If the stop event works, elapsed should be well under 1 second.
    # If we had a plain time.sleep(5), it would be ~5s.
    assert elapsed < 1.0, f"stop() took {elapsed:.2f}s — reconnect backoff was not interrupted"


def test_on_connect_failure_does_not_kill_thread(mocker, fast_reconnect):
    """A raising ``on_connect()`` (e.g. EPROTO when setting modem-control
    lines on a flaky USB hub at startup) must be caught by the loop, route
    through ``handle_error()`` (which disconnects), and let the next
    iteration reconnect — rather than killing the sensor thread."""

    class FlakyOnConnectSensor(MockSensor):
        def __init__(self, name):
            super().__init__(name)
            self.on_connect_calls = 0

        def on_connect(self):
            self.on_connect_calls += 1
            # Fail the first call only; subsequent calls succeed so the
            # loop can stabilise after the disconnect/reconnect cycle.
            if self.on_connect_calls == 1:
                raise OSError(71, "Protocol error")

        def poll(self):
            # Do not auto-terminate after N polls (parent class does that)
            # — we want to inspect a live thread after recovery.
            self.poll_count += 1
            self._stop_event.wait(0.01)

    sensor = FlakyOnConnectSensor("test")
    sensor.should_connect = True
    status_mock = mocker.Mock()

    sensor.start(callback=mocker.Mock(), status_callback=status_mock)

    # The first on_connect call raised; the loop must have caught it,
    # disconnected, reconnected, and started polling.
    wait_for(lambda: sensor.on_connect_calls >= 2)
    wait_for(lambda: sensor.poll_count > 0)
    # The thread should still be alive — i.e. the exception didn't escape
    # to the threading machinery.
    assert sensor.thread is not None and sensor.thread.is_alive()
    # The error must have been reported via the status callback.
    assert any("Protocol error" in str(args) for args in status_mock.call_args_list)

    sensor.stop()


def test_start_is_idempotent_while_alive(mocker, fast_reconnect):
    """Calling start() on a live running sensor must not spawn a second
    thread — the second call is a no-op."""

    # Use a poll that blocks briefly so the thread stays alive for the
    # duration of the test (rather than MockSensor's default
    # stop-after-1000 behaviour).
    class LongLivedMock(MockSensor):
        def poll(self):
            self.poll_count += 1
            # Interruptible wait so stop() returns promptly.
            self._stop_event.wait(0.05)

    sensor = LongLivedMock("test")
    sensor.should_connect = True
    sensor.start(callback=mocker.Mock())
    wait_for(lambda: sensor.poll_count > 0)
    first_thread = sensor.thread
    assert first_thread is not None and first_thread.is_alive()

    # Second start call while the first thread is still alive must not
    # replace the handle.
    sensor.start(callback=mocker.Mock())
    assert sensor.thread is first_thread

    sensor.stop()
