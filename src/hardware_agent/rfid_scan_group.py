"""RFIDScanGroupCoordinator — time-sliced rotation across RFID reader groups.

Readers are organised into *groups*.  At any moment exactly one group is
active (scanning normally); the rest are held in hardware reset via their
configured reset line.  The coordinator cycles through groups in order,
spending ``dwell`` seconds in each slot.

Configuration (via environment, parsed in service.py):

    RFID_SCAN_GROUPS=1,4|2,3   # slot 1: readers 1 & 4 active
                                # slot 2: readers 2 & 3 active
    RFID_SCAN_DWELL=2.0         # seconds per slot (default 2.0)

Groups are applied identically to every nesting box (left and right).
Reader names are matched by suffix, e.g. group number 1 matches both
"left_1" and "right_1".

If RFID_SCAN_GROUPS is not set (or contains only one group), the
coordinator is a no-op and all readers stay permanently active.

Lifecycle:

    coordinator = RFIDScanGroupCoordinator(readers, groups, dwell)
    coordinator.start()   # begins rotating in background thread
    ...
    coordinator.stop()    # waits for current dwell to finish then exits
"""

import logging
import threading
from collections.abc import Sequence

from hardware_agent.rfid_reader import RFIDReader

logger = logging.getLogger(__name__)


def parse_scan_groups(raw: str) -> list[frozenset[int]]:
    """Parse an RFID_SCAN_GROUPS string into a list of frozensets.

    Format: ``"1,4|2,3"``  →  ``[frozenset({1, 4}), frozenset({2, 3})]``

    Raises ValueError for malformed input.
    """
    groups = []
    for slot in raw.split("|"):
        slot = slot.strip()
        if not slot:
            continue
        numbers = frozenset(int(n.strip()) for n in slot.split(",") if n.strip())
        if not numbers:
            raise ValueError(f"Empty group in RFID_SCAN_GROUPS: {raw!r}")
        groups.append(numbers)
    if not groups:
        raise ValueError(f"No groups found in RFID_SCAN_GROUPS: {raw!r}")
    return groups


class RFIDScanGroupCoordinator:
    """Rotates a set of RFIDReaders through scan groups on a timed cycle.

    Each reader is matched to a group by the numeric suffix of its name
    (e.g. ``"left_2"`` has suffix ``2``).  Readers whose suffix does not
    appear in any group are treated as permanently active.

    Parameters
    ----------
    readers:
        All RFIDReader instances to manage.  Readers not covered by any
        group are left permanently active (never paused).
    groups:
        Ordered list of groups as returned by ``parse_scan_groups``.
        Must contain at least two groups; if only one group is provided
        the coordinator logs a warning and does nothing.
    dwell:
        Seconds to spend in each group slot before rotating.
    """

    def __init__(
        self,
        readers: Sequence[RFIDReader],
        groups: list[frozenset[int]],
        dwell: float,
    ):
        self._readers = readers
        self._groups = groups
        self._dwell = dwell
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _suffix(self, reader: RFIDReader) -> int | None:
        """Return the numeric suffix of a reader name (e.g. ``"left_2"`` → 2)."""
        try:
            return int(reader.name.rsplit("_", 1)[-1])
        except (ValueError, IndexError):
            return None

    def _all_managed_readers(self) -> set[RFIDReader]:
        """Readers that appear in at least one group."""
        all_suffixes = set().union(*self._groups)
        return {r for r in self._readers if self._suffix(r) in all_suffixes}

    def _readers_in_group(self, group: frozenset[int]) -> list[RFIDReader]:
        return [r for r in self._readers if self._suffix(r) in group]

    def _readers_not_in_group(self, group: frozenset[int]) -> list[RFIDReader]:
        managed = self._all_managed_readers()
        return [r for r in managed if self._suffix(r) not in group]

    def start(self) -> None:
        if len(self._groups) < 2:
            logger.warning(
                "RFIDScanGroupCoordinator: fewer than 2 groups configured; "
                "rotation disabled, all readers remain active"
            )
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="RFIDScanGroupCoordinator"
        )
        self._thread.start()
        logger.info(
            "RFID scan group rotation started: %d groups, %.1fs dwell",
            len(self._groups),
            self._dwell,
        )

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("RFIDScanGroupCoordinator thread did not exit within %.1fs", timeout)
        self._thread = None
        # Leave all readers in a running state on shutdown so the
        # BaseSensor stop() calls can drain cleanly.
        for reader in self._all_managed_readers():
            reader.resume()

    def _run(self) -> None:
        group_idx = 0
        while not self._stop_event.is_set():
            active_group = self._groups[group_idx]
            to_resume = self._readers_in_group(active_group)
            to_pause = self._readers_not_in_group(active_group)

            # Pause first so there is never a moment where two overlapping
            # groups are simultaneously active (which would defeat the
            # purpose of the rotation). Each call is wrapped individually
            # so a failure on one reader (e.g. a TOCTOU race on serial_conn,
            # or an unexpected exception) does not abort the rest of the
            # rotation — the cycle must continue regardless.
            for reader in to_pause:
                try:
                    reader.pause()
                except Exception as e:
                    logger.warning("[%s] pause() failed during rotation: %s", reader.name, e)

            for reader in to_resume:
                try:
                    reader.resume()
                except Exception as e:
                    logger.warning("[%s] resume() failed during rotation: %s", reader.name, e)

            logger.info(
                "RFID scan group slot %d/%d active — readers: %s; paused: %s",
                group_idx + 1,
                len(self._groups),
                [r.name for r in to_resume],
                [r.name for r in to_pause],
            )

            self._stop_event.wait(self._dwell)
            group_idx = (group_idx + 1) % len(self._groups)
