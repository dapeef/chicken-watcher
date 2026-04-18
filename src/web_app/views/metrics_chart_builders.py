"""
Chart-dataset builders for the metrics page.

Each function here takes already-fetched ORM results and turns them into the
list-of-Chart.js-datasets structures the front-end expects. They contain no
request parsing and no DB lookups beyond the ones the caller has handed in,
so they can be unit-tested cleanly without spinning up a full request.

The module is intentionally dependency-free of ``views.metrics`` — it imports
from ``web_app.analytics`` and ``web_app.models`` directly. This keeps the
circular-import risk off the table and makes the builders cheap to reuse
outside the MetricsView (e.g. from a future DRF endpoint or a management
command).
"""

import json
from collections.abc import Iterable
from datetime import date

from django.db.models import (
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)

from ..analytics import (
    BUCKETS_PER_DAY,
    RIGHT,
    egg_time_of_day_kde,
    gaussian_smooth_circular,
    nesting_time_of_day,
    rolling_average,
)
from ..models import Egg, NestingBoxPresencePeriod

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

# One colour per chicken (cycles if more than 10)
PALETTE = [
    "#0d6efd",  # blue
    "#d63384",  # pink
    "#198754",  # green
    "#fd7e14",  # orange
    "#6610f2",  # indigo
    "#20c997",  # teal
    "#dc3545",  # red
    "#ffc107",  # yellow
    "#0dcaf0",  # cyan
    "#6c757d",  # grey
]

SUM_COLOUR = "#adb5bd"  # grey — dotted, secondary
MEAN_COLOUR = "#212529"  # near-black — solid/bold, primary aggregate
UNKNOWN_COLOUR = "#adb5bd"  # grey — unattributed eggs series / pie slices


# ---------------------------------------------------------------------------
# Common dataset fragments
# ---------------------------------------------------------------------------


def _sum_series(per_hen: list[list], n_cols: int) -> list:
    """Element-wise sum across ``per_hen`` rows, treating ``None`` as 'absent'.

    ``n_cols`` is the expected length of the output — must be given
    explicitly because ``per_hen`` may be empty (no chickens selected,
    or only unknown-chicken eggs in scope).

    Returns ``None`` for positions where every contributing hen was
    ``None``, otherwise the sum of the non-None values. When
    ``per_hen`` is empty, every position is ``None``.
    """
    out: list = []
    for i in range(n_cols):
        vals = [per_hen[h][i] for h in range(len(per_hen)) if per_hen[h][i] is not None]
        out.append(sum(vals) if vals else None)
    return out


def _active_counts(per_hen: list[list], n_cols: int) -> list[int]:
    """Element-wise count of hens that had a non-None value at each
    index. ``n_cols`` must match what was used with :func:`_sum_series`."""
    return [sum(1 for h in range(len(per_hen)) if per_hen[h][i] is not None) for i in range(n_cols)]


def _sum_dataset(data: list, *, dashed: bool = True) -> dict:
    return {
        "label": "Sum",
        "data": data,
        "tension": 0.3,
        "pointRadius": 0,
        "borderColor": SUM_COLOUR,
        "backgroundColor": SUM_COLOUR,
        "borderWidth": 3,
        **({"borderDash": [4, 4]} if dashed else {}),
    }


def _mean_dataset(data: list) -> dict:
    return {
        "label": "Mean",
        "data": data,
        "tension": 0.3,
        "pointRadius": 0,
        "borderColor": MEAN_COLOUR,
        "backgroundColor": MEAN_COLOUR,
        "borderWidth": 3,
    }


# ---------------------------------------------------------------------------
# Egg production (and quality breakdown) — main line chart
# ---------------------------------------------------------------------------


def build_egg_prod_datasets(
    chosen: list,
    data_date_labels: list,
    window: int,
    base_egg_filter: Q,
    show_sum: bool,
    show_mean: bool,
    include_unknown: bool,
    data_start: date,
    end: date,
    unknown_colour: str = UNKNOWN_COLOUR,
) -> list[dict]:
    """Build Chart.js dataset dicts for an egg-production-over-time chart.

    ``base_egg_filter`` is a ``Q`` object ANDed with the chicken/date
    filter before querying eggs — use it to restrict to e.g.
    ``Q(quality='messy')``.

    The returned list always contains one dataset per chicken in
    ``chosen``, optionally an "Unknown" series, and optionally "Sum"
    and "Mean" aggregate lines.
    """
    from django.utils import timezone  # local to keep import cost out of hot path

    eggs_qs = (
        Egg.objects.filter(
            Q(chicken__in=chosen) & base_egg_filter,
            laid_at__date__range=(data_start, end),
        )
        .values("chicken_id", "laid_at__date")
        .annotate(cnt=Count("id"))
    )

    per_hen_counts: dict[int, dict[date, int]] = {c.pk: {} for c in chosen}
    for row in eggs_qs:
        per_hen_counts[row["chicken_id"]][row["laid_at__date"]] = row["cnt"]

    datasets = []
    raw_counts_per_hen = []

    for idx, hen in enumerate(chosen):
        colour = PALETTE[idx % len(PALETTE)]
        dob = hen.date_of_birth
        dod = hen.date_of_death
        counts = [
            per_hen_counts[hen.pk].get(d, 0) if dob <= d <= (dod or timezone.localdate()) else None
            for d in data_date_labels
        ]
        raw_counts_per_hen.append(counts)
        rolled = rolling_average(counts, window, RIGHT)[window:]
        datasets.append(
            {
                "label": hen.name,
                "data": rolled,
                "tension": 0.3,
                "pointRadius": 0,
                "borderColor": colour,
                "backgroundColor": colour,
            }
        )

    if include_unknown:
        unknown_qs = (
            Egg.objects.filter(
                Q(chicken__isnull=True) & base_egg_filter,
                laid_at__date__range=(data_start, end),
            )
            .values("laid_at__date")
            .annotate(cnt=Count("id"))
        )
        unknown_daily: dict[date, int] = {row["laid_at__date"]: row["cnt"] for row in unknown_qs}
        unknown_counts = [unknown_daily.get(d, 0) for d in data_date_labels]
        raw_counts_per_hen.append(unknown_counts)
        rolled_unknown = rolling_average(unknown_counts, window, RIGHT)[window:]
        datasets.append(
            {
                "label": "Unknown",
                "data": rolled_unknown,
                "tension": 0.3,
                "pointRadius": 0,
                "borderColor": unknown_colour,
                "backgroundColor": unknown_colour,
            }
        )

    if show_sum or show_mean:
        n_cols = len(data_date_labels)
        sum_counts = _sum_series(raw_counts_per_hen, n_cols)

        if show_sum:
            rolled_sum = rolling_average(sum_counts, window, RIGHT)[window:]
            datasets.append(_sum_dataset(rolled_sum))

        if show_mean:
            n_active = _active_counts(raw_counts_per_hen, n_cols)
            mean_counts = [
                (sum_counts[i] / n_active[i])
                if (sum_counts[i] is not None and n_active[i] > 0)
                else None
                for i in range(n_cols)
            ]
            rolled_mean = rolling_average(mean_counts, window, RIGHT)[window:]
            datasets.append(_mean_dataset(rolled_mean))

    return datasets


# ---------------------------------------------------------------------------
# Time-of-day — egg-laying KDE
# ---------------------------------------------------------------------------


def build_tod_egg_datasets(
    chosen: list,
    eggs_by_chicken: dict[int, list],
    *,
    kde_bandwidth: int,
    show_sum: bool,
    show_mean: bool,
    include_unknown: bool,
    unknown_eggs: Iterable = (),
) -> list[dict]:
    """Build Chart.js datasets for the egg time-of-day KDE chart.

    Takes pre-batched ``eggs_by_chicken`` (chicken.pk → list[Egg]) and
    (optionally) ``unknown_eggs``. Each series is a circular Gaussian
    KDE evaluated at :data:`BUCKETS_PER_DAY` points.
    """
    datasets: list[dict] = []
    kde_per_hen: list[list[float]] = []

    for idx, hen in enumerate(chosen):
        colour = PALETTE[idx % len(PALETTE)]
        kde = egg_time_of_day_kde(eggs_by_chicken.get(hen.pk, []), bandwidth=kde_bandwidth)
        kde_per_hen.append(kde)
        datasets.append(
            {
                "label": hen.name,
                "data": kde,
                "borderColor": colour,
                "backgroundColor": colour,
                "fill": False,
                "tension": 0.4,
                "pointRadius": 0,
            }
        )

    if include_unknown:
        unknown_kde = egg_time_of_day_kde(unknown_eggs, bandwidth=kde_bandwidth)
        # Include in kde_per_hen so Sum/Mean pick it up. Mean keeps
        # len(chosen) as denominator (unknown is not a named chicken).
        kde_per_hen.append(unknown_kde)
        datasets.append(
            {
                "label": "Unknown",
                "data": unknown_kde,
                "borderColor": UNKNOWN_COLOUR,
                "backgroundColor": UNKNOWN_COLOUR,
                "fill": False,
                "tension": 0.4,
                "pointRadius": 0,
            }
        )

    if show_sum or show_mean:
        # When no hens contributed, sum over an empty generator is 0,
        # which gives a flat-line "Sum" series — matches the original
        # behaviour.
        kde_sum = [
            sum(kde_per_hen[h][b] for h in range(len(kde_per_hen))) for b in range(BUCKETS_PER_DAY)
        ]
        if show_sum:
            datasets.append(
                {
                    "label": "Sum",
                    "data": [round(v, 6) for v in kde_sum],
                    "borderColor": SUM_COLOUR,
                    "backgroundColor": SUM_COLOUR,
                    "fill": False,
                    "tension": 0.4,
                    "pointRadius": 0,
                    "borderDash": [4, 4],
                    "borderWidth": 3,
                }
            )
        if show_mean and chosen:
            n = len(chosen)
            datasets.append(
                {
                    "label": "Mean",
                    "data": [round(v / n, 6) for v in kde_sum],
                    "borderColor": MEAN_COLOUR,
                    "backgroundColor": MEAN_COLOUR,
                    "fill": False,
                    "tension": 0.4,
                    "pointRadius": 0,
                    "borderWidth": 3,
                }
            )

    return datasets


# ---------------------------------------------------------------------------
# Time-of-day — nesting presence
# ---------------------------------------------------------------------------


def build_tod_nest_datasets(
    chosen: list,
    periods_by_chicken: dict[int, list],
    *,
    nest_sigma: int,
    show_sum: bool,
    show_mean: bool,
) -> list[dict]:
    """Build Chart.js datasets for the nesting time-of-day chart."""
    datasets: list[dict] = []
    nest_per_hen: list[list[int]] = []

    for idx, hen in enumerate(chosen):
        colour = PALETTE[idx % len(PALETTE)]
        counts = nesting_time_of_day(periods_by_chicken.get(hen.pk, []))
        nest_per_hen.append(counts)
        smoothed = gaussian_smooth_circular(counts, nest_sigma)
        datasets.append(
            {
                "label": hen.name,
                "data": smoothed,
                "borderColor": colour,
                "backgroundColor": colour,
                "fill": False,
                "tension": 0.4,
                "pointRadius": 0,
            }
        )

    if show_sum or show_mean:
        nest_sum_raw = [
            sum(nest_per_hen[h][b] for h in range(len(chosen))) for b in range(BUCKETS_PER_DAY)
        ]
        nest_sum = gaussian_smooth_circular(nest_sum_raw, nest_sigma)
        if show_sum:
            datasets.append(
                {
                    "label": "Sum",
                    "data": nest_sum,
                    "borderColor": SUM_COLOUR,
                    "backgroundColor": SUM_COLOUR,
                    "fill": False,
                    "tension": 0.4,
                    "pointRadius": 0,
                    "borderDash": [4, 4],
                    "borderWidth": 3,
                }
            )
        if show_mean and chosen:
            n = len(chosen)
            datasets.append(
                {
                    "label": "Mean",
                    "data": [round(v / n, 2) for v in nest_sum],
                    "borderColor": MEAN_COLOUR,
                    "backgroundColor": MEAN_COLOUR,
                    "fill": False,
                    "tension": 0.4,
                    "pointRadius": 0,
                    "borderWidth": 3,
                }
            )

    return datasets


# ---------------------------------------------------------------------------
# Flock count (alive-hens-per-day step chart)
# ---------------------------------------------------------------------------


def build_flock_count_dataset(
    chosen: list,
    date_labels: list,
    today: date,
) -> dict:
    """Count of chosen chickens alive per day across the date range."""
    flock_counts = [
        sum(1 for hen in chosen if hen.date_of_birth <= d <= (hen.date_of_death or today))
        for d in date_labels
    ]
    return {
        "label": "Flock size",
        "data": flock_counts,
        "borderColor": "#495057",
        "backgroundColor": "rgba(73,80,87,0.1)",
        "fill": True,
        "tension": 0.3,
        "pointRadius": 0,
        "stepped": True,
    }


# ---------------------------------------------------------------------------
# Nesting-box preference pies (visits / time / eggs)
# ---------------------------------------------------------------------------


def _pie_colour(label: str, idx: int) -> str:
    return UNKNOWN_COLOUR if label == "Unknown" else PALETTE[idx % len(PALETTE)]


def build_nesting_box_preference_charts(
    chosen: list,
    start: date,
    end: date,
    *,
    include_unknown: bool,
    normal_egg_filter: Q,
) -> dict:
    """Build the three nesting-box preference pie charts.

    Returns a dict with three keys: ``visits``, ``time``, ``eggs`` —
    each a Chart.js-compatible ``{labels, datasets}`` structure.

    ``visits`` counts :class:`NestingBoxPresencePeriod` rows per box;
    ``time`` sums their durations in seconds; ``eggs`` counts eggs per
    box (widened by ``include_unknown`` if set).
    """
    box_qs = (
        NestingBoxPresencePeriod.objects.filter(
            chicken__in=chosen,
            started_at__date__range=(start, end),
        )
        .annotate(
            duration_secs=ExpressionWrapper(
                F("ended_at") - F("started_at"),
                output_field=DurationField(),
            )
        )
        .values("nesting_box__name")
        .annotate(
            visits=Count("id"),
            total_duration=Sum("duration_secs"),
        )
        .order_by("nesting_box__name")
    )

    box_labels_raw: list = []
    box_visits: list[int] = []
    box_seconds: list[int] = []
    for row in box_qs:
        box_labels_raw.append(row["nesting_box__name"])
        box_visits.append(row["visits"])
        duration = row["total_duration"]
        box_seconds.append(int(duration.total_seconds()) if duration is not None else 0)

    box_labels = [name.title() if name else "Unknown" for name in box_labels_raw]

    # Eggs per nesting box
    egg_box_filter = Q(chicken__in=chosen) & normal_egg_filter
    if include_unknown:
        egg_box_filter |= Q(chicken__isnull=True) & normal_egg_filter
    egg_box_qs = (
        Egg.objects.filter(
            egg_box_filter,
            laid_at__date__range=(start, end),
        )
        .values("nesting_box__name")
        .annotate(egg_count=Count("id"))
        .order_by("nesting_box__name")
    )
    egg_box_labels = [
        r["nesting_box__name"].title() if r["nesting_box__name"] else "Unknown" for r in egg_box_qs
    ]
    egg_box_counts = [r["egg_count"] for r in egg_box_qs]

    pie_colours = [_pie_colour(label, i) for i, label in enumerate(box_labels)]
    egg_pie_colours = [_pie_colour(label, i) for i, label in enumerate(egg_box_labels)]

    return {
        "visits": {
            "labels": box_labels,
            "datasets": [{"data": box_visits, "backgroundColor": pie_colours}],
        },
        "time": {
            "labels": box_labels,
            "datasets": [{"data": box_seconds, "backgroundColor": pie_colours}],
        },
        "eggs": {
            "labels": egg_box_labels,
            "datasets": [{"data": egg_box_counts, "backgroundColor": egg_pie_colours}],
        },
    }


# ---------------------------------------------------------------------------
# Egg production vs age
# ---------------------------------------------------------------------------


def build_age_prod_datasets(
    chosen: list,
    *,
    today: date,
    age_window: int,
    normal_egg_filter: Q,
    chosen_dob_by_id: dict[int, date],
    show_sum: bool,
    show_mean: bool,
) -> tuple[list[int], list[dict]]:
    """Build the egg-production-vs-age chart.

    X-axis: age in days. Each series is one chicken's eggs/day as a
    function of her age, rolling-averaged with a warm-up period of
    ``age_window`` days.

    Returns ``(age_display_labels, datasets)`` so the caller doesn't
    have to re-compute the x-axis labels.
    """
    max_age_days = 0
    for hen in chosen:
        dod = hen.date_of_death or today
        if dod >= hen.date_of_birth:
            max_age_days = max(max_age_days, (dod - hen.date_of_birth).days)

    # age_display_labels: [0, 1, …, max_age]  (x-axis)
    # age_data_labels: [-age_window, …, max_age]  (warm-up + display)
    # After rolling and [age_window:], output index i maps to age i.
    age_display_labels = list(range(max_age_days + 1))
    age_data_labels = list(range(-age_window, max_age_days + 1))

    datasets: list[dict] = []
    age_raw_counts_per_hen: list[list] = []

    if not (chosen and max_age_days > 0):
        return age_display_labels, datasets

    # One query for every chosen hen's egg-per-day aggregates; group
    # by chicken_id in Python. Previously this ran one query per hen.
    age_rows = (
        Egg.objects.filter(Q(chicken__in=chosen) & normal_egg_filter)
        .values("chicken_id", "laid_at__date")
        .annotate(cnt=Count("id"))
    )
    age_counts_by_chicken: dict[int, dict] = {hen.pk: {} for hen in chosen}
    for row in age_rows:
        hen_id = row["chicken_id"]
        age_day = (row["laid_at__date"] - chosen_dob_by_id[hen_id]).days
        age_counts_by_chicken[hen_id][age_day] = row["cnt"]

    for idx, hen in enumerate(chosen):
        colour = PALETTE[idx % len(PALETTE)]
        dob = hen.date_of_birth
        dod = hen.date_of_death or today
        max_alive_age = (dod - dob).days
        age_counts = age_counts_by_chicken[hen.pk]
        counts_by_age = [
            age_counts.get(a, 0) if 0 <= a <= max_alive_age else None for a in age_data_labels
        ]
        age_raw_counts_per_hen.append(counts_by_age)

        rolled = rolling_average(counts_by_age, age_window, RIGHT)[age_window:]
        datasets.append(
            {
                "label": hen.name,
                "data": rolled,
                "tension": 0.3,
                "pointRadius": 0,
                "borderColor": colour,
                "backgroundColor": colour,
            }
        )

    if show_sum or show_mean:
        n_cols = len(age_data_labels)
        age_sum_counts = _sum_series(age_raw_counts_per_hen, n_cols)

        if show_sum:
            rolled_sum = rolling_average(age_sum_counts, age_window, RIGHT)[age_window:]
            datasets.append(_sum_dataset(rolled_sum))

        if show_mean:
            n_active = _active_counts(age_raw_counts_per_hen, n_cols)
            age_mean_counts = [
                (age_sum_counts[i] / n_active[i])
                if (age_sum_counts[i] is not None and n_active[i] > 0)
                else None
                for i in range(n_cols)
            ]
            rolled_mean = rolling_average(age_mean_counts, age_window, RIGHT)[age_window:]
            datasets.append(_mean_dataset(rolled_mean))

    return age_display_labels, datasets


# ---------------------------------------------------------------------------
# Convenience: serialise chart data to the context-dict the template wants
# ---------------------------------------------------------------------------


def pie_context_json(pie: dict) -> str:
    """Serialise a single pie dict (from build_nesting_box_preference_charts)
    to the JSON string the template's ``*_json`` context keys expect."""
    return json.dumps(pie)
