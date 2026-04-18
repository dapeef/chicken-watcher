"""
Metrics page: multi-chicken overlays for egg production, egg time-of-day KDE,
and nesting time-of-day frequency.

URL params
----------
chickens        – repeated: ?chickens=1&chickens=3  (pk list; empty = all)
show_sum        – "1" to include a sum series
show_mean       – "1" to include a mean series
include_unknown – "1" to include unattributed eggs
include_non_saleable – "1" to include edible + messy eggs in main production
                       chart and time-of-day / nesting box charts (default: off)
start           – YYYY-MM-DD  (default: 90 days ago)
end             – YYYY-MM-DD  (default: today)
w               – rolling window in days for egg production chart (default: 7)
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.db.models import Q
from django.http import QueryDict
from django.utils import timezone
from django.views.generic import TemplateView

from ..analytics import BUCKET_MINUTES, BUCKETS_PER_DAY
from ..models import Chicken, Egg, NestingBoxPresencePeriod
from .metrics_chart_builders import (
    build_age_prod_datasets,
    build_egg_prod_datasets,
    build_flock_count_dataset,
    build_nesting_box_preference_charts,
    build_tod_egg_datasets,
    build_tod_nest_datasets,
)
from .metrics_chart_builders import (
    # Re-exported so existing test imports keep working. _build_egg_prod_datasets
    # was the private name; the public build_egg_prod_datasets is the same
    # function with no underscore.
    build_egg_prod_datasets as _build_egg_prod_datasets,
)

DEFAULT_WINDOW = 7
DEFAULT_AGE_WINDOW = 30
DEFAULT_SPAN = 7
WINDOW_CHOICES = (1, 3, 7, 10, 30, 90)

# Smoothing bandwidth choices for nesting time-of-day chart, in minutes.
# 0 means no smoothing.
NEST_SIGMA_CHOICES = (0, 10, 20, 30, 60)
DEFAULT_NEST_SIGMA = 20

KDE_BANDWIDTH_CHOICES = (5, 10, 25, 45, 60)
DEFAULT_KDE_BANDWIDTH = 25


def _parse_date(txt: str | None) -> date | None:
    if not txt:
        return None
    try:
        return datetime.strptime(txt, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_int_choice(raw: str | None, choices: tuple[int, ...], default: int) -> int:
    """Parse ``raw`` as an int and return it if it's one of ``choices``,
    otherwise return ``default``.

    Collapses the repeated "try int(...), fall back on ValueError, then
    check against whitelist" dance that appeared five times in the
    original MetricsParams parsing.
    """
    try:
        value = int(raw) if raw is not None else default
    except (ValueError, TypeError):
        return default
    return value if value in choices else default


@dataclass(frozen=True)
class MetricsParams:
    """Typed, validated bundle of the query-string parameters the
    metrics page accepts.

    Previously ``MetricsView.get_context_data`` opened with ~80 lines
    of hand-rolled parsing and fallback logic (eight parse-with-
    fallback blocks for dates, windows, sigmas, booleans). This
    dataclass owns that logic so:

    * the view body can focus on the computation it actually does,
    * each parameter's parse / validate rules are in one place,
    * the parser can be unit-tested directly from a ``QueryDict``
      without spinning up a full Django request.
    """

    # Chicken selection
    all_chickens: list
    selected_ids: list[int] = field(default_factory=list)
    chickens_sent: bool = False
    chosen: list = field(default_factory=list)

    # Date range
    start: date | None = None
    end: date | None = None

    # Aggregation / inclusion toggles
    show_sum: bool = False
    show_mean: bool = True
    include_unknown: bool = True
    include_non_saleable: bool = False

    # Rolling / smoothing windows
    window: int = 0
    age_window: int = 0
    nest_sigma: int = 0
    kde_bandwidth: int = 0

    @classmethod
    def from_request(cls, req: QueryDict, all_chickens: list) -> "MetricsParams":
        """Parse a GET-request QueryDict into a fully-validated
        :class:`MetricsParams`."""
        chickens_sent = "chickens_sent" in req
        try:
            selected_ids = [int(i) for i in req.getlist("chickens")]
        except (ValueError, TypeError):
            selected_ids = []

        if chickens_sent:
            chosen = [c for c in all_chickens if c.pk in selected_ids]
        else:
            chosen = list(all_chickens)

        end = _parse_date(req.get("end")) or timezone.localdate()
        start = _parse_date(req.get("start"))
        if not start or start > end:
            start = end - timedelta(days=DEFAULT_SPAN - 1)

        # Boolean toggles. Defaults differ for fresh vs submitted form
        # because the unchecked checkboxes are absent from the POST
        # payload — we need the sentinel to know what "absent" means.
        show_sum = req.get("show_sum", "") == "1"
        show_mean = req.get("show_mean", "" if chickens_sent else "1") == "1"
        include_unknown = req.get("include_unknown", "" if chickens_sent else "1") == "1"
        include_non_saleable = req.get("include_non_saleable", "") == "1"

        window = _parse_int_choice(req.get("w"), WINDOW_CHOICES, DEFAULT_WINDOW)
        age_window = _parse_int_choice(req.get("age_w"), WINDOW_CHOICES, DEFAULT_AGE_WINDOW)
        nest_sigma = _parse_int_choice(
            req.get("nest_sigma"), NEST_SIGMA_CHOICES, DEFAULT_NEST_SIGMA
        )
        kde_bandwidth = _parse_int_choice(
            req.get("kde_bw"), KDE_BANDWIDTH_CHOICES, DEFAULT_KDE_BANDWIDTH
        )

        return cls(
            all_chickens=all_chickens,
            selected_ids=selected_ids,
            chickens_sent=chickens_sent,
            chosen=chosen,
            start=start,
            end=end,
            show_sum=show_sum,
            show_mean=show_mean,
            include_unknown=include_unknown,
            include_non_saleable=include_non_saleable,
            window=window,
            age_window=age_window,
            nest_sigma=nest_sigma,
            kde_bandwidth=kde_bandwidth,
        )

    @property
    def chosen_dob_by_id(self) -> dict[int, date]:
        return {hen.pk: hen.date_of_birth for hen in self.chosen}

    @property
    def normal_egg_filter(self) -> Q:
        """Base filter for the main egg-production / TOD / box-preference
        charts. By default only saleable eggs are shown;
        ``include_non_saleable`` widens this to all eggs."""
        return Q() if self.include_non_saleable else Q(quality="saleable")


__all__ = [
    # Public API
    "MetricsView",
    "MetricsParams",
    "build_egg_prod_datasets",
    # Defaults / choices — consumed by the template and a few tests.
    "DEFAULT_WINDOW",
    "DEFAULT_AGE_WINDOW",
    "DEFAULT_SPAN",
    "DEFAULT_NEST_SIGMA",
    "DEFAULT_KDE_BANDWIDTH",
    "WINDOW_CHOICES",
    "NEST_SIGMA_CHOICES",
    "KDE_BANDWIDTH_CHOICES",
    # Legacy private alias — retained so older tests can ``from
    # web_app.views.metrics import _build_egg_prod_datasets`` without
    # knowing the function moved. New tests should import the public
    # name from ``web_app.views.metrics_chart_builders``.
    "_build_egg_prod_datasets",
]


class MetricsView(TemplateView):
    template_name = "web_app/metrics.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # ── Sidebar params ────────────────────────────────────────────────────
        all_chickens = list(Chicken.objects.order_by("name"))
        params = MetricsParams.from_request(self.request.GET, all_chickens)

        today = timezone.localdate()

        # ── Main egg-production chart + per-quality breakdown ────────────────
        data_start = params.start - timedelta(days=params.window)
        days = (params.end - params.start).days + 1
        date_labels = [params.start + timedelta(days=i) for i in range(days)]
        data_date_labels = [data_start + timedelta(days=i) for i in range(days + params.window)]

        egg_prod_datasets = build_egg_prod_datasets(
            chosen=params.chosen,
            data_date_labels=data_date_labels,
            window=params.window,
            base_egg_filter=params.normal_egg_filter,
            show_sum=params.show_sum,
            show_mean=params.show_mean,
            include_unknown=params.include_unknown,
            data_start=data_start,
            end=params.end,
        )

        # Each quality tier gets its own chart, so the mid-page "quality
        # breakdown" section can show three small line charts alongside.
        quality_prod_datasets: dict[str, list[dict]] = {
            tier: build_egg_prod_datasets(
                chosen=params.chosen,
                data_date_labels=data_date_labels,
                window=params.window,
                base_egg_filter=Q(quality=tier),
                show_sum=params.show_sum,
                show_mean=params.show_mean,
                include_unknown=params.include_unknown,
                data_start=data_start,
                end=params.end,
            )
            for tier in ("saleable", "edible", "messy")
        }

        # ── Time-of-day shared labels ────────────────────────────────────────
        tod_labels = [
            f"{(i * BUCKET_MINUTES) // 60:02d}:{(i * BUCKET_MINUTES) % 60:02d}"
            for i in range(BUCKETS_PER_DAY)
        ]

        # ── Egg time-of-day KDE ──────────────────────────────────────────────
        # Batch-fetch eggs for all chosen hens in one query, then group
        # in Python. (Previously this was N+1.)
        eggs_by_chicken: dict[int, list] = {hen.pk: [] for hen in params.chosen}
        if params.chosen:
            batched_eggs = Egg.objects.filter(
                Q(chicken__in=params.chosen) & params.normal_egg_filter,
                laid_at__date__range=(params.start, params.end),
            ).only("id", "chicken_id", "laid_at")
            for egg in batched_eggs:
                eggs_by_chicken.setdefault(egg.chicken_id, []).append(egg)

        unknown_eggs = []
        if params.include_unknown:
            unknown_eggs = list(
                Egg.objects.filter(
                    Q(chicken__isnull=True) & params.normal_egg_filter,
                    laid_at__date__range=(params.start, params.end),
                )
            )

        tod_egg_datasets = build_tod_egg_datasets(
            chosen=params.chosen,
            eggs_by_chicken=eggs_by_chicken,
            kde_bandwidth=params.kde_bandwidth,
            show_sum=params.show_sum,
            show_mean=params.show_mean,
            include_unknown=params.include_unknown,
            unknown_eggs=unknown_eggs,
        )

        # ── Nesting time-of-day ──────────────────────────────────────────────
        # Same batch-then-group pattern as the egg KDE above.
        periods_by_chicken: dict[int, list] = {hen.pk: [] for hen in params.chosen}
        if params.chosen:
            batched_periods = NestingBoxPresencePeriod.objects.filter(
                chicken__in=params.chosen,
                started_at__date__range=(params.start, params.end),
            ).only("id", "chicken_id", "started_at", "ended_at")
            for p in batched_periods:
                periods_by_chicken.setdefault(p.chicken_id, []).append(p)

        tod_nest_datasets = build_tod_nest_datasets(
            chosen=params.chosen,
            periods_by_chicken=periods_by_chicken,
            nest_sigma=params.nest_sigma,
            show_sum=params.show_sum,
            show_mean=params.show_mean,
        )

        # ── Remaining charts ─────────────────────────────────────────────────
        flock_count_dataset = build_flock_count_dataset(
            chosen=params.chosen, date_labels=date_labels, today=today
        )

        pies = build_nesting_box_preference_charts(
            chosen=params.chosen,
            start=params.start,
            end=params.end,
            include_unknown=params.include_unknown,
            normal_egg_filter=params.normal_egg_filter,
        )

        age_prod_labels, age_prod_datasets = build_age_prod_datasets(
            chosen=params.chosen,
            today=today,
            age_window=params.age_window,
            normal_egg_filter=params.normal_egg_filter,
            chosen_dob_by_id=params.chosen_dob_by_id,
            show_sum=params.show_sum,
            show_mean=params.show_mean,
        )

        # ── Context ──────────────────────────────────────────────────────────
        ctx.update(
            {
                # Sidebar state (for re-rendering the form)
                "all_chickens": all_chickens,
                "selected_ids": params.selected_ids,
                "chickens_sent": params.chickens_sent,
                "show_sum": params.show_sum,
                "show_mean": params.show_mean,
                "include_unknown": params.include_unknown,
                "include_non_saleable": params.include_non_saleable,
                "today": today.isoformat(),
                "earliest_dob": (
                    min(
                        (c.date_of_birth for c in all_chickens),
                        default=today,
                    )
                ).isoformat(),
                "start": params.start.isoformat(),
                "end": params.end.isoformat(),
                "window": params.window,
                "window_choices": WINDOW_CHOICES,
                "age_window": params.age_window,
                "nest_sigma": params.nest_sigma,
                "nest_sigma_choices": NEST_SIGMA_CHOICES,
                "kde_bandwidth": params.kde_bandwidth,
                "kde_bandwidth_choices": KDE_BANDWIDTH_CHOICES,
                # Per-chart JSON strings, retained for the in-context
                # assertions that the test suite relies on.
                "egg_prod_labels_json": json.dumps([d.isoformat() for d in date_labels]),
                "egg_prod_datasets_json": json.dumps(egg_prod_datasets),
                "saleable_prod_datasets_json": json.dumps(quality_prod_datasets["saleable"]),
                "edible_prod_datasets_json": json.dumps(quality_prod_datasets["edible"]),
                "messy_prod_datasets_json": json.dumps(quality_prod_datasets["messy"]),
                "flock_count_dataset_json": json.dumps(flock_count_dataset),
                "tod_labels_json": json.dumps(tod_labels),
                "tod_egg_datasets_json": json.dumps(tod_egg_datasets),
                "tod_nest_datasets_json": json.dumps(tod_nest_datasets),
                "nesting_box_visits_json": json.dumps(pies["visits"]),
                "nesting_box_time_json": json.dumps(pies["time"]),
                "nesting_box_eggs_json": json.dumps(pies["eggs"]),
                "age_prod_labels_json": json.dumps(age_prod_labels),
                "age_prod_datasets_json": json.dumps(age_prod_datasets),
                # Consolidated native-Python blob for metrics_charts.js.
                "metrics_chart_data": {
                    "show_mean": params.show_mean,
                    "egg_prod_labels": [d.isoformat() for d in date_labels],
                    "egg_prod_datasets": egg_prod_datasets,
                    "saleable_prod_datasets": quality_prod_datasets["saleable"],
                    "edible_prod_datasets": quality_prod_datasets["edible"],
                    "messy_prod_datasets": quality_prod_datasets["messy"],
                    "flock_count_dataset": flock_count_dataset,
                    "tod_labels": tod_labels,
                    "tod_egg_datasets": tod_egg_datasets,
                    "tod_nest_datasets": tod_nest_datasets,
                    "nesting_box_time": pies["time"],
                    "nesting_box_visits": pies["visits"],
                    "nesting_box_eggs": pies["eggs"],
                    "age_prod_labels": age_prod_labels,
                    "age_prod_datasets": age_prod_datasets,
                },
            }
        )
        return ctx
