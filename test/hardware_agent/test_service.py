"""
Tests for hardware_agent.service.run_agent.

The interesting behaviour to cover is the graceful-shutdown path:
SIGTERM/SIGINT should unblock the main thread and trigger
manager.stop_all() so serial/GPIO/camera resources are released
before the process exits.
"""

import signal
import threading
import time

import pytest

from hardware_agent import service


def _common_patches(mocker, mock_manager):
    mocker.patch.object(service, "HardwareManager", return_value=mock_manager)
    mocker.patch.object(service, "LGPIOFactory", None)
    # Prevent the scan-group coordinator from spawning real threads.
    mocker.patch.object(service, "RFIDScanGroupCoordinator")


def test_run_agent_registers_signal_handlers(mocker):
    """run_agent must install handlers for SIGTERM and SIGINT so a
    ``docker stop`` or Ctrl-C unwinds cleanly."""
    mock_manager = mocker.Mock()
    _common_patches(mocker, mock_manager)

    mock_signal = mocker.patch.object(service.signal, "signal")

    # Run run_agent in a thread and interrupt it promptly with SIGTERM.
    t = threading.Thread(target=service.run_agent, daemon=True)
    t.start()

    # Wait until both handlers have been registered.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if mock_signal.call_count >= 2:
            break
        time.sleep(0.01)
    else:
        pytest.fail("run_agent did not register signal handlers in time")

    # Grab the installed handler — it's whatever was passed as the
    # second arg to signal.signal() — and invoke it directly to
    # simulate SIGTERM arriving.
    registered_signals = [call.args[0] for call in mock_signal.call_args_list]
    assert signal.SIGTERM in registered_signals
    assert signal.SIGINT in registered_signals

    handler = None
    for call in mock_signal.call_args_list:
        if call.args[0] == signal.SIGTERM:
            handler = call.args[1]
            break
    assert handler is not None

    handler(signal.SIGTERM, None)

    t.join(timeout=2.0)
    assert not t.is_alive(), "run_agent did not exit after SIGTERM"

    # On shutdown, the manager's stop_all must have been called.
    mock_manager.stop_all.assert_called_once()


def test_run_agent_sigint_handler_also_triggers_shutdown(mocker):
    """Mirror of the SIGTERM test but for SIGINT (Ctrl-C)."""
    mock_manager = mocker.Mock()
    _common_patches(mocker, mock_manager)

    mock_signal = mocker.patch.object(service.signal, "signal")

    t = threading.Thread(target=service.run_agent, daemon=True)
    t.start()

    # Wait for handler registration
    deadline = time.time() + 2.0
    while time.time() < deadline and mock_signal.call_count < 2:
        time.sleep(0.01)
    assert mock_signal.call_count >= 2

    # Grab the SIGINT handler and invoke it.
    sigint_handler = None
    for call in mock_signal.call_args_list:
        if call.args[0] == signal.SIGINT:
            sigint_handler = call.args[1]
            break
    assert sigint_handler is not None

    sigint_handler(signal.SIGINT, None)

    t.join(timeout=2.0)
    assert not t.is_alive()
    mock_manager.stop_all.assert_called_once()


def test_run_agent_stop_all_runs_even_if_event_wait_interrupted(mocker):
    """If shutdown_event.wait is interrupted by an exception (not a
    normal return), manager.stop_all must still run because it's in a
    ``finally`` block."""
    mock_manager = mocker.Mock()
    _common_patches(mocker, mock_manager)

    # Make threading.Event.wait raise KeyboardInterrupt the first time
    # it's called inside run_agent.
    original_event_cls = threading.Event

    class ExplodingEvent(original_event_cls):
        def wait(self, timeout=None):
            raise KeyboardInterrupt("simulated")

    mocker.patch.object(service.threading, "Event", ExplodingEvent)

    with pytest.raises(KeyboardInterrupt):
        service.run_agent()

    mock_manager.stop_all.assert_called_once()
