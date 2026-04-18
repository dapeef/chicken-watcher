"""
Tests for web_app.analytics — the pure-numerical helpers used by metrics
views and the chicken-detail page.

These tests were previously scattered:
  - TestNestingTimeOfDay / TestEggTimeOfDayKde lived in test_chickens.py
    (views), even though the code under test had no Django dependency.
  - TestGaussianSmoothCircular lived in test_metrics.py (views).
  - RollingAverageTests lived in test_utils.py.

Consolidating them here matches the source-side move from the
``views/`` layer into ``web_app/analytics.py``.
"""

from datetime import datetime, timezone as dt_timezone
from math import isclose

import pytest

from web_app.analytics import (
    BUCKET_MINUTES,
    BUCKETS_PER_DAY,
    CENTER,
    LEFT,
    RIGHT,
    egg_time_of_day_kde,
    gaussian_smooth_circular,
    nesting_time_of_day,
    rolling_average,
)
from .factories import EggFactory, NestingBoxPresencePeriodFactory


def _utc(hour: int, minute: int = 0, day: int = 1) -> datetime:
    """Return a UTC-aware datetime on an arbitrary fixed date."""
    return datetime(2024, 1, day, hour, minute, tzinfo=dt_timezone.utc)


def _make_period(started_at: datetime, ended_at: datetime):
    """Build an unsaved NestingBoxPresencePeriod-like object for unit tests."""
    return NestingBoxPresencePeriodFactory.build(
        started_at=started_at, ended_at=ended_at
    )


def _make_egg(laid_at: datetime):
    """Build an unsaved Egg-like object for unit tests."""
    return EggFactory.build(laid_at=laid_at)


# ---------------------------------------------------------------------------
# nesting_time_of_day
# ---------------------------------------------------------------------------


class TestNestingTimeOfDay:
    def test_empty_periods(self):
        counts = nesting_time_of_day([])
        assert len(counts) == BUCKETS_PER_DAY
        assert all(c == 0 for c in counts)

    def test_single_period_within_one_bucket(self):
        # 10:02 – 10:07 falls entirely inside bucket 10:00–10:10 (index 60)
        period = _make_period(_utc(10, 2), _utc(10, 7))
        counts = nesting_time_of_day([period])
        bucket = (10 * 60) // BUCKET_MINUTES  # index 60
        assert counts[bucket] == 1
        assert sum(counts) == 1

    def test_period_spanning_two_buckets(self):
        # 10:05 – 10:15 spans buckets 10:00 (index 60) and 10:10 (index 61)
        period = _make_period(_utc(10, 5), _utc(10, 15))
        counts = nesting_time_of_day([period])
        assert counts[60] == 1
        assert counts[61] == 1
        assert sum(counts) == 2

    def test_same_chicken_same_bucket_two_different_days(self):
        # Two periods on different days, both in the 10:00 bucket → count = 2
        p1 = _make_period(_utc(10, 2, day=1), _utc(10, 7, day=1))
        p2 = _make_period(_utc(10, 2, day=2), _utc(10, 7, day=2))
        counts = nesting_time_of_day([p1, p2])
        bucket = (10 * 60) // BUCKET_MINUTES
        assert counts[bucket] == 2

    def test_same_day_two_periods_same_bucket_counted_once(self):
        # Two periods on the same day, both in the 10:00 bucket → count = 1
        p1 = _make_period(_utc(10, 0, day=1), _utc(10, 5, day=1))
        p2 = _make_period(_utc(10, 5, day=1), _utc(10, 9, day=1))
        counts = nesting_time_of_day([p1, p2])
        bucket = (10 * 60) // BUCKET_MINUTES
        assert counts[bucket] == 1

    def test_period_spanning_midnight(self):
        # 23:55 day 1 to 00:05 day 2 — spans bucket 23:50 and 00:00
        p = _make_period(_utc(23, 55, day=1), _utc(0, 5, day=2))
        counts = nesting_time_of_day([p])
        assert counts[0] == 1  # 00:00 bucket, hit on day 2
        assert counts[143] == 1  # 23:50 bucket, hit on day 1


# ---------------------------------------------------------------------------
# egg_time_of_day_kde
# ---------------------------------------------------------------------------


class TestEggTimeOfDayKde:
    def test_empty_returns_all_zeros(self):
        result = egg_time_of_day_kde([])
        assert len(result) == BUCKETS_PER_DAY
        assert all(v == 0.0 for v in result)

    def test_result_length(self):
        egg = _make_egg(_utc(10, 0))
        result = egg_time_of_day_kde([egg])
        assert len(result) == BUCKETS_PER_DAY

    def test_single_egg_peak_near_its_time(self):
        egg = _make_egg(_utc(10, 0))
        result = egg_time_of_day_kde([egg])
        peak_bucket = result.index(max(result))
        peak_minutes = peak_bucket * BUCKET_MINUTES
        assert abs(peak_minutes - 600) <= BUCKET_MINUTES

    def test_all_values_non_negative(self):
        eggs = [_make_egg(_utc(h)) for h in range(0, 24, 3)]
        result = egg_time_of_day_kde(eggs)
        assert all(v >= 0 for v in result)

    def test_integrates_to_approximately_one(self):
        # Summing all buckets and multiplying by BUCKET_MINUTES gives
        # total probability mass, which should be ≈ 1.
        eggs = [_make_egg(_utc(h)) for h in range(0, 24, 2)]
        result = egg_time_of_day_kde(eggs)
        total = sum(result) * BUCKET_MINUTES
        assert abs(total - 1.0) < 0.05

    def test_midnight_egg_wraps_symmetrically(self):
        egg = _make_egg(_utc(0, 0))
        result = egg_time_of_day_kde([egg])
        assert result[0] == max(result)
        assert abs(result[1] - result[143]) < 1e-6

    def test_larger_bandwidth_gives_broader_peak(self):
        egg = _make_egg(_utc(10, 0))
        narrow = egg_time_of_day_kde([egg], bandwidth=10)
        wide = egg_time_of_day_kde([egg], bandwidth=60)
        assert max(wide) < max(narrow)
        assert narrow.index(max(narrow)) == wide.index(max(wide))

    def test_very_small_bandwidth_produces_spike(self):
        egg = _make_egg(_utc(10, 0))
        result = egg_time_of_day_kde([egg], bandwidth=1)
        peak_bucket = (10 * 60) // BUCKET_MINUTES
        assert result[peak_bucket] == max(result)


# ---------------------------------------------------------------------------
# gaussian_smooth_circular
# ---------------------------------------------------------------------------


class TestGaussianSmoothCircular:
    def test_sigma_zero_returns_floats_equal_to_input(self):
        counts = list(range(BUCKETS_PER_DAY))
        result = gaussian_smooth_circular(counts, 0)
        assert result == [float(v) for v in counts]

    def test_output_length_is_buckets_per_day(self):
        counts = [1] * BUCKETS_PER_DAY
        assert len(gaussian_smooth_circular(counts, 20)) == BUCKETS_PER_DAY

    def test_all_zeros_stays_all_zeros(self):
        counts = [0] * BUCKETS_PER_DAY
        result = gaussian_smooth_circular(counts, 20)
        assert all(v == 0.0 for v in result)

    def test_single_spike_peak_at_spike_location(self):
        counts = [0] * BUCKETS_PER_DAY
        spike_bucket = 60  # 10:00
        counts[spike_bucket] = 10
        result = gaussian_smooth_circular(counts, 20)
        assert result.index(max(result)) == spike_bucket

    def test_single_spike_symmetric_falloff(self):
        counts = [0] * BUCKETS_PER_DAY
        spike_bucket = 60
        counts[spike_bucket] = 10
        result = gaussian_smooth_circular(counts, 20)
        assert abs(result[spike_bucket - 1] - result[spike_bucket + 1]) < 1e-6

    def test_wraps_at_midnight(self):
        counts = [0] * BUCKETS_PER_DAY
        counts[0] = 10
        result = gaussian_smooth_circular(counts, 30)
        # Last bucket should be non-zero due to circular wrap
        assert result[-1] > 0
        # And by symmetry result[-1] ≈ result[1]
        assert abs(result[-1] - result[1]) < 1e-4

    def test_smoothing_reduces_peak_value(self):
        counts = [0] * BUCKETS_PER_DAY
        counts[60] = 10
        result = gaussian_smooth_circular(counts, 20)
        assert max(result) < 10

    def test_smoothing_preserves_total_mass(self):
        counts = [1] * BUCKETS_PER_DAY
        result = gaussian_smooth_circular(counts, 20)
        assert all(abs(v - 1.0) < 1e-4 for v in result)


# ---------------------------------------------------------------------------
# rolling_average
# ---------------------------------------------------------------------------


def _assert_list_almost_equal(a, b, rel_tol=1e-7):
    assert len(a) == len(b)
    for x, y in zip(a, b):
        if x is None or y is None:
            assert x is None and y is None
        else:
            assert isclose(x, y, rel_tol=rel_tol)


class TestRollingAverage:
    def test_center_alignment(self):
        _assert_list_almost_equal(
            rolling_average([1, 2, 3, 4, 5], 3, alignment=CENTER),
            [None, 2.0, 3.0, 4.0, None],
        )

    def test_left_alignment(self):
        _assert_list_almost_equal(
            rolling_average([1, 2, 3, 4, 5], 3, alignment=LEFT),
            [2.0, 3.0, 4.0, None, None],
        )

    def test_right_alignment(self):
        _assert_list_almost_equal(
            rolling_average([1, 2, 3, 4, 5], 3, alignment=RIGHT),
            [None, None, 2.0, 3.0, 4.0],
        )

    def test_window_equals_one(self):
        _assert_list_almost_equal(rolling_average([10, 20, 30], 1), [10, 20, 30])

    def test_invalid_alignment_raises_value_error(self):
        """The old implementation raised bare ``Exception``; the
        rewrite uses ``ValueError`` which is the conventional choice
        for "bad argument value"."""
        with pytest.raises(ValueError, match="alignment"):
            rolling_average([1, 2, 3], window=2, alignment="diagonal")

    def test_none_padding_propagates_through_window(self):
        """A ``None`` inside the window makes that output point
        ``None``, regardless of the values around it."""
        _assert_list_almost_equal(
            rolling_average([None, 1, 2, 3, 4, 5, None, 5, 4, 3, 2, 1, None], 3),
            [None, None, 2.0, 3.0, 4.0, None, None, None, 4.0, 3.0, 2.0, None, None],
        )
