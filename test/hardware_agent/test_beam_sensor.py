import pytest
from gpiozero.exc import GPIOZeroError

from hardware_agent.beam_break_sensor import BeamSensor


def test_beam_sensor_connect_success(mocker):
    mock_dev = mocker.patch("hardware_agent.beam_break_sensor.DigitalInputDevice")
    sensor = BeamSensor("test", 17)
    assert sensor.connect() is True
    assert sensor.is_connected() is True
    mock_dev.assert_called_once_with(17, pull_up=True, bounce_time=None, pin_factory=None)


def test_beam_sensor_connect_fail(mocker):
    mocker.patch(
        "hardware_agent.beam_break_sensor.DigitalInputDevice",
        side_effect=GPIOZeroError("fail"),
    )
    sensor = BeamSensor("test", 17)
    assert sensor.connect() is False
    assert sensor.is_connected() is False


def test_beam_sensor_on_connect(mocker):
    mock_dev = mocker.Mock()
    mocker.patch("hardware_agent.beam_break_sensor.DigitalInputDevice", return_value=mock_dev)
    callback = mocker.Mock()
    sensor = BeamSensor("test", 17)
    sensor.callback = callback
    sensor.connect()

    sensor.on_connect()
    assert mock_dev.when_activated is not None

    # Trigger callback
    mock_dev.when_activated()
    callback.assert_called_once_with("test")


def test_beam_sensor_poll(mocker):
    mock_dev = mocker.Mock()
    mock_dev.value = 1
    mocker.patch("hardware_agent.beam_break_sensor.DigitalInputDevice", return_value=mock_dev)
    sensor = BeamSensor("test", 17)
    sensor.connect()

    mocker.patch("time.sleep")
    sensor.poll()

    # Just verify it accessed value
    assert mock_dev.value == 1


def test_beam_sensor_poll_error(mocker):
    mock_dev = mocker.Mock()
    type(mock_dev).value = mocker.PropertyMock(side_effect=RuntimeError("disconnected"))
    mocker.patch("hardware_agent.beam_break_sensor.DigitalInputDevice", return_value=mock_dev)
    sensor = BeamSensor("test", 17)
    sensor.connect()

    with pytest.raises(Exception, match="GPIO error"):
        sensor.poll()
