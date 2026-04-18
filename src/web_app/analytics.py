"""
Pure-numerical / analytics functions that the metrics and chicken-detail
views need. Kept as a dedicated module (rather than living in ``views/``
or ``utils.py``) because:

* the logic is data-shape-driven, not HTTP-driven, so it can be unit-
  tested without the web layer,
* multiple views need the same functions, and
* it's a natural home for any future analytics work (e.g. egg-weight
  trends, seasonal patterns) without growing a junk-drawer ``utils.py``.

Contents:

* Time-of-day bucketing constants (:data:`BUCKET_MINUTES`,
  :data:`BUCKETS_PER_DAY`).
* :func:`nesting_time_of_day` — presence-period → day-frequency histogram.
* :func:`egg_time_of_day_kde` — egg-laying time → circular Gaussian KDE.
* :func:`gaussian_smooth_circular` — smooth a day-long histogram with a
  circular Gaussian kernel.
* :func:`rolling_average` — classic rolling mean with left/right/centre
  alignment and ``None``-padding.
"""

from __future__ import annotations

import math
from datetime import timedelta, timezone as dt_timezone
from math import ceil, floor
from typing import Iterable, Literal, Sequence

# ---------------------------------------------------------------------------
# Time-of-day bucketing
# ---------------------------------------------------------------------------

# Width of each time-of-day bucket in minutes. At 10 minutes we get 144
# buckets per day — fine resolution for hourly patterns, coarse enough to
# smooth out noise.
BUCKET_MINUTES = 10
BUCKETS_PER_DAY = 24 * 60 // BUCKET_MINUTES  # 144


# ---------------------------------------------------------------------------
# Rolling average
# ---------------------------------------------------------------------------

Alignment = Literal["left", "right", "center"]
LEFT: Alignment = "left"
RIGHT: Alignment = "right"
CENTER: Alignment = "center"


def rolling_average(
    data: Sequence[float | None],
    window: int,
    alignment: Alignment = CENTER,
) -> list[float | None]:
    """Classic rolling-mean with three alignment modes.

    * ``CENTER`` (default): output[i] is the mean of
      ``data[i - window//2 .. i + window//2]``. Edges are ``None``.
    * ``LEFT``: values shifted left — the mean of a window ending at i
      sits at the *start* of that window.
    * ``RIGHT``: values shifted right — the mean of a window starting at
      i sits at the *end* of that window.

    Any ``None`` value in the window makes that output point ``None``.
    """
    window_before = ceil(window / 2) - 1
    window_after = floor(window / 2)

    start = window_before
    end = len(data) - window_after - 1

    buf = list(data[:window])

    rolling_avg: list[float | None] = []

    for i, _ in enumerate(data):
        if start <= i <= end:
            if None in buf:
                rolling_avg.append(None)
            else:
                rolling_avg.append(sum(buf) / len(buf))

            buf.pop(0)
            if i + window_after + 1 < len(data):
                buf.append(data[i + window_after + 1])

        else:
            rolling_avg.append(None)

    if alignment == LEFT:
        rolling_avg = rolling_avg[start:] + [None] * window_before
    elif alignment == RIGHT:
        rolling_avg = [None] * window_after + rolling_avg[: end + 1]
    elif alignment == CENTER:
        pass
    else:
        raise ValueError(f"Unknown rolling average alignment: {alignment}")

    return rolling_avg


# ---------------------------------------------------------------------------
# Circular Gaussian smoothing (for time-of-day histograms)
# ---------------------------------------------------------------------------


def gaussian_smooth_circular(counts: Sequence[int], sigma_minutes: int) -> list[float]:
    """Apply a circular Gaussian smooth to a day-long histogram.

    ``counts`` must have exactly :data:`BUCKETS_PER_DAY` entries. The day
    is treated as circular so the kernel wraps correctly at midnight.

    Returns a list of floats rounded to 4 decimal places.
    ``sigma_minutes=0`` returns the original counts as floats, unchanged.
    """
    if sigma_minutes == 0:
        return [float(v) for v in counts]

    day_minutes = 24 * 60
    sigma = sigma_minutes
    n = BUCKETS_PER_DAY
    result = []
    for i in range(n):
        x = i * BUCKET_MINUTES
        total_weight = 0.0
        weighted_sum = 0.0
        for j in range(n):
            y = j * BUCKET_MINUTES
            # Circular distance, wrapped to [-day/2, day/2]
            diff = x - y
            diff = (diff + day_minutes // 2) % day_minutes - day_minutes // 2
            w = math.exp(-0.5 * (diff / sigma) ** 2)
            weighted_sum += w * counts[j]
            total_weight += w
        result.append(round(weighted_sum / total_weight, 4))
    return result


# ---------------------------------------------------------------------------
# Nesting presence by time-of-day
# ---------------------------------------------------------------------------


def nesting_time_of_day(periods: Iterable) -> list[int]:
    """Given an iterable of :class:`NestingBoxPresencePeriod` instances,
    return a list of :data:`BUCKETS_PER_DAY` counts.

    Each bucket represents a :data:`BUCKET_MINUTES`-wide window of the
    day in **UTC**. UTC is used deliberately: these are solar/biological
    measurements (chickens don't observe DST), so wall-clock adjustments
    like BST would distort the pattern.

    The value for a bucket is the number of distinct calendar days on
    which the chicken was present in a nesting box during that
    time-of-day window.
    """
    # days_seen[bucket] = set of date objects on which the chicken was
    # present during that bucket's time-of-day window
    days_seen: list[set] = [set() for _ in range(BUCKETS_PER_DAY)]

    for period in periods:
        local_start = period.started_at.astimezone(dt_timezone.utc)
        local_end = period.ended_at.astimezone(dt_timezone.utc)

        # Walk forward in BUCKET_MINUTES steps from the start of the
        # period, capping at local_end. For each step record which
        # calendar date and which bucket index it falls in.
        cursor = local_start.replace(second=0, microsecond=0)
        # Snap cursor back to the start of its bucket
        cursor = cursor.replace(
            minute=(cursor.minute // BUCKET_MINUTES) * BUCKET_MINUTES
        )

        while cursor < local_end:
            bucket = (cursor.hour * 60 + cursor.minute) // BUCKET_MINUTES
            days_seen[bucket].add(cursor.date())
            cursor += timedelta(minutes=BUCKET_MINUTES)

    return [len(s) for s in days_seen]


# ---------------------------------------------------------------------------
# Egg time-of-day KDE
# ---------------------------------------------------------------------------

# Bandwidth for egg KDE in minutes. ~25 min gives a smooth but responsive curve.
KDE_BANDWIDTH_MINUTES = 25


def egg_time_of_day_kde(
    eggs: Iterable, bandwidth: int = KDE_BANDWIDTH_MINUTES
) -> list[float]:
    """Given an iterable of :class:`Egg` instances, return a list of
    :data:`BUCKETS_PER_DAY` density values using a circular Gaussian KDE.

    Times are in **UTC** (no DST adjustment) to give solar-relative readings.

    Each egg contributes a Gaussian kernel centred on its UTC time-of-day
    (in minutes). The day is treated as circular (1440 minutes), so
    kernels wrap correctly at midnight. The final curve is the sum of
    all kernels, normalised so the area under it equals 1.

    ``bandwidth`` — Gaussian sigma in minutes. Larger → smoother.

    Returns a list of :data:`BUCKETS_PER_DAY` floats rounded to 6 dp.
    """
    day_minutes = 24 * 60  # 1440

    times = []
    for egg in eggs:
        t = egg.laid_at.astimezone(dt_timezone.utc)
        times.append(t.hour * 60 + t.minute + t.second / 60)

    if not times:
        return [0.0] * BUCKETS_PER_DAY

    sigma = bandwidth
    n = len(times)

    result = []
    for i in range(BUCKETS_PER_DAY):
        x = i * BUCKET_MINUTES  # centre of this bucket in minutes
        total = 0.0
        for t in times:
            # Evaluate the Gaussian at the three closest circular copies
            # (t - DAY, t, t + DAY) to handle wrap-around at midnight.
            for offset in (-day_minutes, 0, day_minutes):
                diff = x - (t + offset)
                total += math.exp(-0.5 * (diff / sigma) ** 2)
        result.append(total / (n * sigma * math.sqrt(2 * math.pi)))

    # Round for compact JSON
    return [round(v, 6) for v in result]
