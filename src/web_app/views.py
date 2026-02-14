import json
from datetime import timedelta, date, datetime

from django import db
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView, ListView, DetailView, CreateView
from django.shortcuts import render

from .forms import EggForm
from .models import Egg, Chicken, NestingBoxPresence, HardwareSensor, NestingBoxImage
from django.db.models import Count, Max, Q

from .utils import rolling_average, RIGHT


def get_dashboard_context():
    today_start = timezone.localtime().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    now = timezone.localtime()

    eggs_today_qs = Egg.objects.filter(laid_at__range=(today_start, now))

    # Latest presence for each box
    if db.connection.vendor == "postgresql":
        latest_presence = (
            NestingBoxPresence.objects.filter(present_at__gte=today_start)
            .order_by("nesting_box_id", "-present_at")
            .distinct("nesting_box_id")
        )
    else:
        # Fallback for SQLite: get the latest presence for each nesting box manually or just show recent ones
        latest_presence = []
        box_ids = (
            NestingBoxPresence.objects.filter(present_at__gte=today_start)
            .values_list("nesting_box_id", flat=True)
            .distinct()
        )
        for b_id in box_ids:
            p = (
                NestingBoxPresence.objects.filter(
                    nesting_box_id=b_id, present_at__gte=today_start
                )
                .order_by("-present_at")
                .first()
            )
            if p:
                latest_presence.append(p)

    return {
        "eggs_today": eggs_today_qs.count(),
        "laid_chickens": Chicken.objects.filter(egg__in=eggs_today_qs)
        .distinct()
        .order_by("name"),
        "latest_presence": latest_presence,
        "latest_events": Egg.objects.filter(laid_at__gte=today_start)
        .select_related("chicken", "nesting_box")
        .order_by("-laid_at")[:10],
        "sensors": HardwareSensor.objects.all().order_by("name"),
        "latest_image": NestingBoxImage.objects.order_by("-created_at").first(),
    }


class DashboardView(TemplateView):
    template_name = "web_app/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_dashboard_context())
        return ctx


def partial_eggs_today(request):
    return render(request, "web_app/partials/_eggs_today.html", get_dashboard_context())


def partial_laid_chickens(request):
    return render(
        request, "web_app/partials/_laid_chickens.html", get_dashboard_context()
    )


def partial_sensors(request):
    return render(request, "web_app/partials/_sensors.html", get_dashboard_context())


def partial_latest_image(request):
    return render(
        request, "web_app/partials/_latest_image.html", get_dashboard_context()
    )


def partial_latest_presence(request):
    return render(
        request, "web_app/partials/_latest_presence.html", get_dashboard_context()
    )


def partial_latest_events(request):
    return render(
        request, "web_app/partials/_latest_events.html", get_dashboard_context()
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


class EggListView(ListView):
    model = Egg
    template_name = "web_app/egg_list.html"

    def get_queryset(self):
        qs = Egg.objects

        sort_param = self.request.GET.get("sort", "-laid_at")
        qs = qs.order_by(sort_param)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sort"] = self.request.GET.get("sort", "-laid_at")
        ctx["headers"] = [
            ("chicken", "Chicken"),
            ("nesting_box", "Nesting box"),
            ("laid_at", "Laid at"),
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
        data_start = start - timedelta(days=window)

        days = (end - start).days + 1
        date_labels = [start + timedelta(days=i) for i in range(days)]
        data_date_labels = [
            data_start + timedelta(days=i) for i in range(days + window)
        ]

        # ------------ aggregate eggs ------------
        eggs = (
            Egg.objects.filter(laid_at__date__range=(data_start, end))
            .exclude(chicken=None)
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
        datasets = []
        for idx, (hen_id, info) in enumerate(per_hen.items()):
            dod = Chicken.objects.get(id=hen_id).date_of_death
            dob = Chicken.objects.get(id=hen_id).date_of_birth
            counts = [
                info["counts"].get(d, 0)
                if dob <= d <= (dod or datetime.today().date())
                else None
                for d in data_date_labels
            ]

            rolling = rolling_average(counts, window, RIGHT)

            rolling = rolling[window:]

            datasets.append(
                {
                    "label": info["name"],
                    "data": rolling,
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


class EggCreateView(CreateView):
    model = Egg
    form_class = EggForm
    template_name = "web_app/egg_form.html"
    success_url = reverse_lazy("egg_list")
