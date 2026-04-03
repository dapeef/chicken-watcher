import json
import math
from datetime import timedelta, date, datetime, timezone as dt_timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic import ListView, DetailView
from django.db.models import Count, Max, Q
from django.utils import timezone

from ..models import Chicken, Egg, NestingBoxPresencePeriod
from ..utils import rolling_average
from .timeline_utils import (
    parse_date_range,
    egg_item,
    period_item,
    empty_range_response,
)


class ChickenListView(ListView):
    model = Chicken
    template_name = "web_app/chicken_list.html"

    def get_queryset(self):
        qs = (
            Chicken.objects.with_egg_metrics(30)
            .annotate(
                eggs_total=Count("egg"),
                last_egg=Max("egg__laid_at"),
            )
            .select_related()  # nothing to prefetch here but keeps pattern
        )

        sort_param = self.request.GET.get("sort", "name")
        qs = qs.order_by(sort_param)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sort"] = self.request.GET.get("sort", "name")
        ctx["headers"] = [
            ("name", "Name"),
            ("eggs_per_day", "Eggs/d (last 30 days)"),
            ("eggs_total", "Eggs total"),
            ("last_egg", "Last egg"),
            ("date_of_birth", "DoB"),
            ("date_of_death", "DoD"),
        ]
        return ctx


class ChickenDetailView(DetailView):
    model = Chicken
    template_name = "web_app/chicken_detail.html"
    context_object_name = "hen"

    DAYS_BACK = 60  # how many days to plot

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        chicken = self.object

        # ------------------------------------------------------------
        # 1) Egg-per-day series + 10-day rolling mean
        # ------------------------------------------------------------
        today = date.today()
        start = today - timedelta(days=self.DAYS_BACK - 1)

        eggs = (
            Egg.objects.filter(chicken=chicken, laid_at__date__gte=start)
            .values("laid_at__date")
            .annotate(cnt=Count("id"))
        )
        counts_by_day = {row["laid_at__date"]: row["cnt"] for row in eggs}

        labels, daily = [], []
        window = 10

        for i in range(self.DAYS_BACK):
            d = start + timedelta(days=i)
            labels.append(d.isoformat())
            c = counts_by_day.get(d, 0)
            daily.append(c)

        rolling = rolling_average(daily, window)

        ctx["chart_labels"] = json.dumps(labels)
        ctx["chart_daily"] = json.dumps(daily)
        ctx["chart_rolling"] = json.dumps(rolling)

        # ------------------------------------------------------------
        # 2) Time-of-day charts (shared labels)
        # ------------------------------------------------------------
        tod_labels = [
            f"{(i * BUCKET_MINUTES) // 60:02d}:{(i * BUCKET_MINUTES) % 60:02d}"
            for i in range(BUCKETS_PER_DAY)
        ]
        ctx["tod_labels"] = json.dumps(tod_labels)

        all_periods = NestingBoxPresencePeriod.objects.filter(chicken=chicken)
        ctx["tod_nesting_counts"] = json.dumps(nesting_time_of_day(all_periods))

        all_eggs = Egg.objects.filter(chicken=chicken)
        ctx["tod_egg_kde"] = json.dumps(egg_time_of_day_kde(all_eggs))

        # ------------------------------------------------------------
        # 3) Quick stats
        # ------------------------------------------------------------
        stats = Egg.objects.filter(chicken=chicken).aggregate(
            total=Count("id"),
            last=Max("laid_at"),
            last30=Count(
                "id", filter=Q(laid_at__gte=timezone.now() - timedelta(days=30))
            ),
        )
        ctx["stats"] = stats
        return ctx


BUCKET_MINUTES = 10
BUCKETS_PER_DAY = 24 * 60 // BUCKET_MINUTES  # 144


def nesting_time_of_day(periods):
    """
    Given an iterable of NestingBoxPresencePeriod instances, return a list of
    BUCKETS_PER_DAY counts.

    Each bucket represents a BUCKET_MINUTES-wide window of the day in UTC.
    UTC is used deliberately: these are solar/biological measurements (chickens
    don't observe DST), so wall-clock adjustments like BST would distort the
    pattern.

    The value is the number of distinct calendar days on which this chicken
    was present in a nesting box during that time-of-day window.
    """
    # days_seen[bucket] = set of date objects on which the chicken was present
    days_seen = [set() for _ in range(BUCKETS_PER_DAY)]

    for period in periods:
        # Convert to UTC — intentionally not local time, to avoid DST distortion
        local_start = period.started_at.astimezone(dt_timezone.utc)
        local_end = period.ended_at.astimezone(dt_timezone.utc)

        # Walk forward in BUCKET_MINUTES steps from the start of the period,
        # capping at local_end. For each step record which calendar date and
        # which bucket index it falls in.
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


# Bandwidth for egg KDE in minutes. ~25 min gives a smooth but responsive curve.
KDE_BANDWIDTH_MINUTES = 25


def egg_time_of_day_kde(eggs):
    """
    Given an iterable of Egg instances, return a list of BUCKETS_PER_DAY
    density values using a circular Gaussian KDE.

    Times are in UTC (no DST adjustment) to give solar-relative readings.

    Each egg contributes a Gaussian kernel centred on its UTC time-of-day
    (in minutes). The day is treated as circular (1440 minutes), so kernels
    wrap correctly at midnight. The final curve is the sum of all kernels,
    normalised so that the area under it equals 1.

    Returns a list of BUCKETS_PER_DAY floats rounded to 4 decimal places.
    """
    DAY_MINUTES = 24 * 60  # 1440

    # Collect time-of-day in minutes (UTC)
    times = []
    for egg in eggs:
        t = egg.laid_at.astimezone(dt_timezone.utc)
        times.append(t.hour * 60 + t.minute + t.second / 60)

    if not times:
        return [0.0] * BUCKETS_PER_DAY

    sigma = KDE_BANDWIDTH_MINUTES
    n = len(times)

    result = []
    for i in range(BUCKETS_PER_DAY):
        x = i * BUCKET_MINUTES  # centre of this bucket in minutes
        total = 0.0
        for t in times:
            # Evaluate the Gaussian at the three closest circular copies
            # (t - DAY, t, t + DAY) to handle wrap-around at midnight
            for offset in (-DAY_MINUTES, 0, DAY_MINUTES):
                diff = x - (t + offset)
                total += math.exp(-0.5 * (diff / sigma) ** 2)
        result.append(total / (n * sigma * math.sqrt(2 * math.pi)))

    # Round for compact JSON
    return [round(v, 6) for v in result]


def chicken_timeline_data(request, pk):
    chicken = get_object_or_404(Chicken, pk=pk)

    try:
        start, end = parse_date_range(request)
    except (ValueError, TypeError, OverflowError):
        return empty_range_response(request)

    eggs = Egg.objects.filter(
        chicken=chicken, laid_at__range=(start, end)
    ).select_related("nesting_box")

    periods = NestingBoxPresencePeriod.objects.filter(
        chicken=chicken, started_at__lte=end, ended_at__gte=start
    ).select_related("nesting_box")

    items = [egg_item(e) for e in eggs] + [period_item(p) for p in periods]

    return JsonResponse(items, safe=False)
