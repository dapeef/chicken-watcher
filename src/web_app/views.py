import json
from datetime import timedelta, date, datetime
from math import floor, ceil
from typing import List

from django.utils import timezone
from django.views.generic import TemplateView, ListView, DetailView
from .models import Egg, Chicken, NestingBoxPresence
from django.db.models import Count, Max, Q

LEFT = "left"
RIGHT = "right"
CENTER = "center"

def rolling_average(data: List[float], window: int, alignment: str=CENTER) -> List[float]:
    window_before = ceil(window / 2) - 1
    window_after = floor(window / 2)

    start = window_before
    end = len(data) - window_after - 1

    buf = data[:window]

    rolling_avg = []

    for i, d in enumerate(data):
        if start <= i <= end:
            rolling_avg.append(sum(buf) / len(buf))

            buf.pop(0)
            if i + window_after + 1 < len(data):
                buf.append(data[i + window_after + 1])


        else:
            rolling_avg.append(None)

    match alignment:
        case "left":
            rolling_avg = rolling_avg[start:] + [None] * window_before
        case "right":
            rolling_avg = [None] * window_after + rolling_avg[:end + 1]
        case "center":
            pass
        case _:
            raise Exception(f"Unknown rolling average alignment: {alignment}")

    return rolling_avg


class DashboardView(TemplateView):
    template_name = "web_app/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        today_start = timezone.localtime().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        now = timezone.localtime()

        eggs_today_qs = Egg.objects.filter(laid_at__range=(today_start, now))
        ctx["eggs_today"] = eggs_today_qs.count()
        ctx["laid_chickens"] = (
            Chicken.objects.filter(egg__in=eggs_today_qs).distinct().order_by("name")
        )

        latest_presence = (
            NestingBoxPresence.objects.filter(present_at__gte=today_start)
            .order_by("nesting_box_id", "-present_at")
            .distinct("nesting_box_id")
        )
        ctx["latest_presence"] = latest_presence

        ctx["latest_events"] = (
            Egg.objects.filter(laid_at__gte=today_start)
            .select_related("chicken", "nesting_box")
            .order_by("-laid_at")[:10]
        )
        return ctx


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
        window = 3

        for i in range(self.DAYS_BACK):
            d = start + timedelta(days=i)
            labels.append(d.isoformat())
            c = counts_by_day.get(d, 0)
            daily.append(c)

        rolling = rolling_average(daily, window, LEFT)

        ctx["chart_labels"] = json.dumps(labels)
        ctx["chart_daily"] = json.dumps(daily)
        ctx["chart_rolling"] = json.dumps(rolling)

        # ------------------------------------------------------------
        # 2) Nesting-box presence last 24 h
        # ------------------------------------------------------------
        now = timezone.localtime()
        since = now - timedelta(hours=24)
        presence = (
            NestingBoxPresence.objects.filter(chicken=chicken, present_at__gte=since)
            .select_related("nesting_box")
            .order_by("present_at")
        )
        ctx["presence_events"] = presence

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


class NestingBoxListView(TemplateView):
    pass


class EggProductionView(TemplateView):
    template_name = "web_app/egg_production.html"

    DEFAULT_WINDOW = 30
    DEFAULT_SPAN = 60  # fallback when no date filter supplied

    def _parse_date(self, txt: str | None) -> date | None:
        if not txt:
            return None
        try:
            return datetime.strptime(txt, "%Y-%m-%d").date()
        except ValueError:
            return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # ------------ read GET params ------------
        window = int(self.request.GET.get("w", self.DEFAULT_WINDOW))
        if window not in (1, 3, 7, 10, 30, 90):
            window = self.DEFAULT_WINDOW

        end = self._parse_date(self.request.GET.get("end")) or date.today()
        start = self._parse_date(self.request.GET.get("start"))
        if not start or start >= end:
            start = end - timedelta(days=self.DEFAULT_SPAN - 1)

        days = (end - start).days + 1
        date_labels = [start + timedelta(days=i) for i in range(days)]

        # ------------ aggregate eggs ------------
        eggs = (
            Egg.objects.filter(laid_at__date__range=(start, end))
            .values("chicken_id", "chicken__name", "laid_at__date")
            .annotate(cnt=Count("id"))
        )

        # build mapping: {hen_id: {date: cnt}}
        per_hen = {}
        for row in eggs:
            per_hen.setdefault(
                row["chicken_id"], {"name": row["chicken__name"], "counts": {}}
            )["counts"][row["laid_at__date"]] = row["cnt"]

        # ------------ build Chart.js datasets ------------
        palette = [
            "#0d6efd",
            "#198754",
            "#dc3545",
            "#fd7e14",
            "#20c997",
            "#6f42c1",
            "#0dcaf0",
            "#ffc107",
            "#6610f2",
            "#d63384",
        ]

        datasets = []
        for idx, (hen_id, info) in enumerate(per_hen.items()):
            counts = [info["counts"].get(d, 0) for d in date_labels]

            # rolling average
            roll, buf = [], []
            for c in counts:
                buf.append(c)
                if len(buf) > window:
                    buf.pop(0)
                roll.append(round(sum(buf) / len(buf), 2))

            color = palette[idx % len(palette)]
            datasets.append(
                {
                    "label": info["name"],
                    "data": roll,
                    "borderColor": color,
                    "backgroundColor": color,
                    "tension": 0.3,
                    "pointRadius": 0,
                }
            )

        ctx.update(
            {
                "labels_json": json.dumps([d.isoformat() for d in date_labels]),
                "datasets_json": json.dumps(datasets),
                "window": window,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "window_choices": (1, 3, 7, 10, 30, 90),
            }
        )
        return ctx
