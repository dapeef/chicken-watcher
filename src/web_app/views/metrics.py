"""
Metrics page: multi-chicken overlays for egg production, egg time-of-day KDE,
and nesting time-of-day frequency.

URL params
----------
chickens    – repeated: ?chickens=1&chickens=3  (pk list; empty = all)
show_sum    – "1" to include a sum series
show_mean   – "1" to include a mean series
start       – YYYY-MM-DD  (default: 60 days ago)
end         – YYYY-MM-DD  (default: today)
w           – rolling window in days for egg production chart (default: 7)
"""

import json
import math
from datetime import timedelta, date, datetime, timezone as dt_timezone

from django.db.models import Count
from django.views.generic import TemplateView

from ..models import Chicken, Egg, NestingBoxPresencePeriod
from ..utils import rolling_average, RIGHT
from .chickens import (
    nesting_time_of_day,
    egg_time_of_day_kde,
    BUCKET_MINUTES,
    BUCKETS_PER_DAY,
)

DEFAULT_WINDOW = 7
DEFAULT_SPAN = 90
WINDOW_CHOICES = (1, 3, 7, 10, 30, 90)

# Smoothing bandwidth choices for nesting time-of-day chart, in minutes.
# 0 means no smoothing.
NEST_SIGMA_CHOICES = (0, 10, 20, 30, 60)
DEFAULT_NEST_SIGMA = 20

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

SUM_COLOUR = "#adb5bd"  # grey  — dotted, secondary
MEAN_COLOUR = "#212529"  # near-black — solid/bold, primary aggregate


def _gaussian_smooth_circular(counts: list[int], sigma_minutes: int) -> list[float]:
    """
    Apply a circular Gaussian smooth to a list of BUCKETS_PER_DAY integer counts.
    The day is treated as circular so the kernel wraps correctly at midnight.
    Returns a list of floats rounded to 4 decimal places.
    sigma_minutes=0 returns the original counts unchanged (as floats).
    """
    if sigma_minutes == 0:
        return [float(v) for v in counts]

    DAY_MINUTES = 24 * 60
    sigma = sigma_minutes
    n = BUCKETS_PER_DAY
    result = []
    for i in range(n):
        x = i * BUCKET_MINUTES
        total_weight = 0.0
        weighted_sum = 0.0
        for j in range(n):
            y = j * BUCKET_MINUTES
            # Circular distance
            diff = x - y
            # Wrap to [-DAY_MINUTES/2, DAY_MINUTES/2]
            diff = (diff + DAY_MINUTES // 2) % DAY_MINUTES - DAY_MINUTES // 2
            w = math.exp(-0.5 * (diff / sigma) ** 2)
            weighted_sum += w * counts[j]
            total_weight += w
        result.append(round(weighted_sum / total_weight, 4))
    return result


def _parse_date(txt: str | None) -> date | None:
    if not txt:
        return None
    try:
        return datetime.strptime(txt, "%Y-%m-%d").date()
    except ValueError:
        return None


class MetricsView(TemplateView):
    template_name = "web_app/metrics.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        req = self.request.GET

        # ── Sidebar params ────────────────────────────────────────────────────
        all_chickens = list(Chicken.objects.order_by("name"))

        # Which chickens are selected?
        # "chickens_sent" is a hidden sentinel that is always submitted with the
        # form, so we can distinguish an explicit empty selection from a fresh
        # page load (where no chickens param is present at all).
        chickens_sent = "chickens_sent" in req
        selected_ids = req.getlist("chickens")
        try:
            selected_ids = [int(i) for i in selected_ids]
        except (ValueError, TypeError):
            selected_ids = []

        if chickens_sent:
            # User submitted the form — respect their selection, even if empty
            chosen = [c for c in all_chickens if c.pk in selected_ids]
        else:
            # Fresh page load — default to all chickens
            chosen = list(all_chickens)

        show_sum = req.get("show_sum", "") == "1"
        # Default mean to on for fresh page loads; respect the form value once submitted
        show_mean = req.get("show_mean", "" if chickens_sent else "1") == "1"

        # Date range
        end = _parse_date(req.get("end")) or date.today()
        start = _parse_date(req.get("start"))
        if not start or start >= end:
            start = end - timedelta(days=DEFAULT_SPAN - 1)

        # Rolling window (egg production chart only)
        try:
            window = int(req.get("w", DEFAULT_WINDOW))
        except (ValueError, TypeError):
            window = DEFAULT_WINDOW
        if window not in WINDOW_CHOICES:
            window = DEFAULT_WINDOW

        # Nesting smoothing bandwidth (minutes)
        try:
            nest_sigma = int(req.get("nest_sigma", DEFAULT_NEST_SIGMA))
        except (ValueError, TypeError):
            nest_sigma = DEFAULT_NEST_SIGMA
        if nest_sigma not in NEST_SIGMA_CHOICES:
            nest_sigma = DEFAULT_NEST_SIGMA

        # ── Egg production chart ──────────────────────────────────────────────
        data_start = start - timedelta(days=window)
        days = (end - start).days + 1
        date_labels = [start + timedelta(days=i) for i in range(days)]
        data_date_labels = [
            data_start + timedelta(days=i) for i in range(days + window)
        ]

        # Query eggs for all chosen chickens in one hit
        eggs_qs = (
            Egg.objects.filter(
                chicken__in=chosen,
                laid_at__date__range=(data_start, end),
            )
            .values("chicken_id", "laid_at__date")
            .annotate(cnt=Count("id"))
        )

        # {hen_id: {date: count}}
        per_hen_counts: dict[int, dict[date, int]] = {c.pk: {} for c in chosen}
        for row in eggs_qs:
            per_hen_counts[row["chicken_id"]][row["laid_at__date"]] = row["cnt"]

        egg_prod_datasets = []
        raw_counts_per_hen: list[list[float | None]] = []

        for idx, hen in enumerate(chosen):
            colour = PALETTE[idx % len(PALETTE)]
            dob = hen.date_of_birth
            dod = hen.date_of_death

            counts = [
                per_hen_counts[hen.pk].get(d, 0)
                if dob <= d <= (dod or date.today())
                else None
                for d in data_date_labels
            ]
            raw_counts_per_hen.append(counts)

            rolled = rolling_average(counts, window, RIGHT)[window:]

            egg_prod_datasets.append(
                {
                    "label": hen.name,
                    "data": rolled,
                    "tension": 0.3,
                    "pointRadius": 0,
                    "borderColor": colour,
                    "backgroundColor": colour,
                }
            )

        # Sum / Mean aggregates
        if show_sum or show_mean:
            # Per-day totals across chosen hens (None if ALL hens are None that day)
            n_hens = len(raw_counts_per_hen)
            sum_counts: list[float | None] = []
            for day_idx in range(len(data_date_labels)):
                vals = [
                    raw_counts_per_hen[h][day_idx]
                    for h in range(n_hens)
                    if raw_counts_per_hen[h][day_idx] is not None
                ]
                sum_counts.append(sum(vals) if vals else None)

            if show_sum:
                rolled_sum = rolling_average(sum_counts, window, RIGHT)[window:]
                egg_prod_datasets.append(
                    {
                        "label": "Sum",
                        "data": rolled_sum,
                        "tension": 0.3,
                        "pointRadius": 0,
                        "borderColor": SUM_COLOUR,
                        "backgroundColor": SUM_COLOUR,
                        "borderDash": [4, 4],
                        "borderWidth": 3,
                    }
                )

            if show_mean:
                n_active = [
                    sum(
                        1
                        for h in range(n_hens)
                        if raw_counts_per_hen[h][day_idx] is not None
                    )
                    for day_idx in range(len(data_date_labels))
                ]
                mean_counts: list[float | None] = [
                    (sum_counts[i] / n_active[i])
                    if (sum_counts[i] is not None and n_active[i] > 0)
                    else None
                    for i in range(len(data_date_labels))
                ]
                rolled_mean = rolling_average(mean_counts, window, RIGHT)[window:]
                egg_prod_datasets.append(
                    {
                        "label": "Mean",
                        "data": rolled_mean,
                        "tension": 0.3,
                        "pointRadius": 0,
                        "borderColor": MEAN_COLOUR,
                        "backgroundColor": MEAN_COLOUR,
                        "borderWidth": 3,
                    }
                )

        # ── Time-of-day shared labels ─────────────────────────────────────────
        tod_labels = [
            f"{(i * BUCKET_MINUTES) // 60:02d}:{(i * BUCKET_MINUTES) % 60:02d}"
            for i in range(BUCKETS_PER_DAY)
        ]

        # ── Egg time-of-day KDE (one series per hen + optional sum/mean) ──────
        tod_egg_datasets = []
        kde_per_hen: list[list[float]] = []

        for idx, hen in enumerate(chosen):
            colour = PALETTE[idx % len(PALETTE)]
            hen_eggs = Egg.objects.filter(
                chicken=hen,
                laid_at__date__range=(start, end),
            )
            kde = egg_time_of_day_kde(hen_eggs)
            kde_per_hen.append(kde)
            tod_egg_datasets.append(
                {
                    "label": hen.name,
                    "data": kde,
                    "borderColor": colour,
                    "backgroundColor": colour.rstrip(")")
                    if colour.startswith("rgba")
                    else colour,
                    "fill": False,
                    "tension": 0.4,
                    "pointRadius": 0,
                }
            )

        if show_sum or show_mean:
            kde_sum = [
                sum(kde_per_hen[h][b] for h in range(len(chosen)))
                for b in range(BUCKETS_PER_DAY)
            ]
            if show_sum:
                tod_egg_datasets.append(
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
                tod_egg_datasets.append(
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

        # ── Nesting time-of-day (one series per hen + optional sum/mean) ──────
        tod_nest_datasets = []
        nest_per_hen: list[list[int]] = []

        for idx, hen in enumerate(chosen):
            colour = PALETTE[idx % len(PALETTE)]
            periods = NestingBoxPresencePeriod.objects.filter(
                chicken=hen,
                started_at__date__range=(start, end),
            )
            counts = nesting_time_of_day(periods)
            nest_per_hen.append(counts)
            smoothed = _gaussian_smooth_circular(counts, nest_sigma)
            tod_nest_datasets.append(
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
                sum(nest_per_hen[h][b] for h in range(len(chosen)))
                for b in range(BUCKETS_PER_DAY)
            ]
            nest_sum = _gaussian_smooth_circular(nest_sum_raw, nest_sigma)
            if show_sum:
                tod_nest_datasets.append(
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
                tod_nest_datasets.append(
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

        # ── Flock count chart ─────────────────────────────────────────────────
        # For each day in the display range, count how many of the *chosen*
        # chickens were alive (dob <= day <= dod-or-today).
        today = date.today()
        flock_counts = [
            sum(
                1
                for hen in chosen
                if hen.date_of_birth <= d <= (hen.date_of_death or today)
            )
            for d in date_labels
        ]
        flock_count_dataset = {
            "label": "Flock size",
            "data": flock_counts,
            "borderColor": "#495057",
            "backgroundColor": "rgba(73,80,87,0.1)",
            "fill": True,
            "tension": 0.3,
            "pointRadius": 0,
            "stepped": True,
        }

        # ── Context ───────────────────────────────────────────────────────────
        ctx.update(
            {
                # Sidebar state (for re-rendering the form)
                "all_chickens": all_chickens,
                "selected_ids": selected_ids,
                "chickens_sent": chickens_sent,
                "show_sum": show_sum,
                "show_mean": show_mean,
                "today": date.today().isoformat(),
                "earliest_dob": (
                    min((c.date_of_birth for c in all_chickens), default=date.today())
                ).isoformat(),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "window": window,
                "window_choices": WINDOW_CHOICES,
                "nest_sigma": nest_sigma,
                "nest_sigma_choices": NEST_SIGMA_CHOICES,
                # Chart data
                "egg_prod_labels_json": json.dumps(
                    [d.isoformat() for d in date_labels]
                ),
                "egg_prod_datasets_json": json.dumps(egg_prod_datasets),
                "flock_count_dataset_json": json.dumps(flock_count_dataset),
                "tod_labels_json": json.dumps(tod_labels),
                "tod_egg_datasets_json": json.dumps(tod_egg_datasets),
                "tod_nest_datasets_json": json.dumps(tod_nest_datasets),
            }
        )
        return ctx
