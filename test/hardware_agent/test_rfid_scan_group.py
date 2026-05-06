import time

import pytest

from hardware_agent.rfid_reader import RFIDReader
from hardware_agent.rfid_scan_group import RFIDScanGroupCoordinator, parse_scan_groups

# ---------------------------------------------------------------------------
# parse_scan_groups
# ---------------------------------------------------------------------------


def test_parse_scan_groups_basic():
    result = parse_scan_groups("1,4|2,3")
    assert result == [frozenset({1, 4}), frozenset({2, 3})]


def test_parse_scan_groups_single_group():
    result = parse_scan_groups("1,2,3,4")
    assert result == [frozenset({1, 2, 3, 4})]


def test_parse_scan_groups_three_groups():
    result = parse_scan_groups("1|2|3,4")
    assert result == [frozenset({1}), frozenset({2}), frozenset({3, 4})]


def test_parse_scan_groups_whitespace_tolerant():
    result = parse_scan_groups(" 1 , 4 | 2 , 3 ")
    assert result == [frozenset({1, 4}), frozenset({2, 3})]


def test_parse_scan_groups_invalid_raises():
    with pytest.raises(ValueError):
        parse_scan_groups("1,x|2,3")


def test_parse_scan_groups_empty_raises():
    with pytest.raises(ValueError):
        parse_scan_groups("")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_reader(name: str) -> RFIDReader:
    """Return a disconnected RFIDReader with no serial port (good enough
    for pause/resume state tests that don't touch serial_conn)."""
    return RFIDReader(name, "/dev/null")


# ---------------------------------------------------------------------------
# RFIDReader.pause() / resume()
# ---------------------------------------------------------------------------


def test_pause_sets_paused_flag():
    reader = make_reader("left_1")
    assert not reader._paused.is_set()
    reader.pause()
    assert reader._paused.is_set()


def test_resume_clears_paused_flag():
    reader = make_reader("left_1")
    reader.pause()
    reader.resume()
    assert not reader._paused.is_set()


def test_poll_returns_early_when_paused(mocker):
    """A paused reader must not attempt any serial reads."""
    reader = make_reader("left_1")
    reader.serial_conn = mocker.Mock()
    reader.serial_conn.is_open = True
    reader._paused.set()
    mocker.patch.object(reader._stop_event, "wait")  # don't actually sleep

    reader.poll()

    reader.serial_conn.read.assert_not_called()


def test_pause_drains_buffered_tag_before_asserting_reset(mocker):
    """pause() must deliver any tag already buffered in the serial port
    before asserting the reset line. Without this drain the read would
    wait until the next resume(), introducing unnecessary latency."""
    from test.hardware_agent.test_rfid_reader import MockSerial

    data = b"\x02TAG123X\x03"
    reader = make_reader("left_1")
    reader.serial_conn = MockSerial(data)
    callback = mocker.Mock()
    reader.callback = callback

    reader.pause()

    # The buffered tag must have been delivered immediately.
    callback.assert_called_once_with("left_1", "TAG123")
    # And the reader must now be paused.
    assert reader._paused.is_set()


def test_pause_does_not_drain_when_already_paused(mocker):
    """Calling pause() on an already-paused reader must not attempt
    another drain — it is already gated and the buffer should be empty."""
    from test.hardware_agent.test_rfid_reader import MockSerial

    reader = make_reader("left_1")
    reader.serial_conn = MockSerial(b"\x02TAG123X\x03")
    reader._paused.set()  # already paused
    callback = mocker.Mock()
    reader.callback = callback

    reader.pause()

    callback.assert_not_called()


# ---------------------------------------------------------------------------
# RFIDScanGroupCoordinator — rotation behaviour
# ---------------------------------------------------------------------------


def _make_coordinator(groups_str: str, dwell: float = 0.05):
    readers = [
        make_reader("left_1"),
        make_reader("left_2"),
        make_reader("left_3"),
        make_reader("left_4"),
        make_reader("right_1"),
        make_reader("right_2"),
        make_reader("right_3"),
        make_reader("right_4"),
    ]
    groups = parse_scan_groups(groups_str)
    coordinator = RFIDScanGroupCoordinator(readers, groups, dwell)
    return coordinator, readers


def _readers_by_suffix(readers, suffix: int) -> list[RFIDReader]:
    return [r for r in readers if r.name.endswith(f"_{suffix}")]


def test_coordinator_single_group_does_not_start(caplog):
    """A coordinator with only one group should log a warning and not
    start a rotation thread."""
    coordinator, _ = _make_coordinator("1,2,3,4")
    coordinator.start()
    assert coordinator._thread is None
    assert "fewer than 2 groups" in caplog.text


def test_coordinator_rotates_active_group():
    """After one dwell period the coordinator should have rotated:
    group-2 readers become active and group-1 readers become paused."""
    dwell = 0.05
    coordinator, readers = _make_coordinator("1,4|2,3", dwell=dwell)
    coordinator.start()

    # After just under one dwell: group 1 (readers 1 & 4) should be active.
    time.sleep(dwell * 0.4)
    for r in _readers_by_suffix(readers, 1) + _readers_by_suffix(readers, 4):
        assert not r._paused.is_set(), f"{r.name} should be active in slot 1"
    for r in _readers_by_suffix(readers, 2) + _readers_by_suffix(readers, 3):
        assert r._paused.is_set(), f"{r.name} should be paused in slot 1"

    # After one full dwell: group 2 (readers 2 & 3) should now be active.
    time.sleep(dwell * 1.2)
    for r in _readers_by_suffix(readers, 2) + _readers_by_suffix(readers, 3):
        assert not r._paused.is_set(), f"{r.name} should be active in slot 2"
    for r in _readers_by_suffix(readers, 1) + _readers_by_suffix(readers, 4):
        assert r._paused.is_set(), f"{r.name} should be paused in slot 2"

    coordinator.stop()


def test_coordinator_stop_resumes_all_readers():
    """After stop(), all managed readers must be un-paused so that
    BaseSensor.stop() can drain their poll loops cleanly."""
    coordinator, readers = _make_coordinator("1,4|2,3", dwell=0.05)
    coordinator.start()
    time.sleep(0.03)
    coordinator.stop()

    for r in readers:
        assert not r._paused.is_set(), f"{r.name} should be resumed after stop()"


def test_coordinator_unmanaged_readers_never_paused():
    """Readers whose suffix does not appear in any group must never be
    paused, regardless of which slot is active."""
    readers = [
        make_reader("left_1"),
        make_reader("left_2"),
        make_reader("left_99"),  # not in any group
    ]
    groups = parse_scan_groups("1|2")
    coordinator = RFIDScanGroupCoordinator(readers, groups, dwell=0.05)
    coordinator.start()
    time.sleep(0.15)  # several full rotations
    coordinator.stop()

    unmanaged = next(r for r in readers if r.name == "left_99")
    assert not unmanaged._paused.is_set()


def test_coordinator_pause_before_resume_on_rotation():
    """The coordinator must pause the outgoing group before resuming the
    incoming group — never a moment where two overlapping
    groups are simultaneously active.

    The invariant: within each rotation event, the first action must be a
    pause (holding the outgoing group in reset) before any resume (releasing
    the incoming group). We detect a violation if a resume appears in the
    event stream before the first pause of the same rotation batch.
    """
    events: list[tuple[str, str]] = []  # (reader_name, "pause"/"resume")
    dwell = 0.05

    readers = [make_reader("left_1"), make_reader("left_2")]
    for reader in readers:
        original_pause = reader.pause
        original_resume = reader.resume

        def make_pause(r, op=original_pause):
            def _pause():
                events.append((r.name, "pause"))
                op()

            return _pause

        def make_resume(r, op=original_resume):
            def _resume():
                events.append((r.name, "resume"))
                op()

            return _resume

        reader.pause = make_pause(reader)
        reader.resume = make_resume(reader)

    groups = parse_scan_groups("1|2")
    coordinator = RFIDScanGroupCoordinator(readers, groups, dwell=dwell)
    coordinator.start()
    time.sleep(dwell * 1.5)
    coordinator.stop()

    # Split the event stream into rotation batches: each batch starts when
    # the action switches from "resume" back to "pause" (the next slot begins).
    # Within every batch, all pauses must precede all resumes.
    batch: list[str] = []
    for _, action in events:
        if action == "pause" and "resume" in batch:
            # New batch starting — validate the completed one first.
            batch = ["pause"]
        else:
            batch.append(action)
        # Within the current batch, a resume must not precede the first pause.
        if batch and batch[0] == "resume":
            pytest.fail(
                "resume fired before pause in a rotation batch — "
                "both groups were briefly active simultaneously. "
                f"Full event stream: {events}"
            )
