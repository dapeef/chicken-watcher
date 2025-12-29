import json
from datetime import timedelta, date

from django.utils import timezone
from django.views.generic import TemplateView, ListView, DetailView
from .models import Egg, Chicken, NestingBoxPresence
from django.db.models import Count, Max, Q


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

        # naive “who is inside right now” – last presence record per box
        latest_presence = (
            NestingBoxPresence.objects
            .filter(present_at__gte=today_start)
            .order_by("nesting_box_id", "-present_at")
            .distinct("nesting_box_id")
        )
        ctx["current_presence"] = latest_presence

        ctx["latest_events"] = (
            Egg.objects.filter(laid_at__gte=today_start)
            .select_related("chicken", "nesting_box")
            .order_by("-laid_at")[:10]
        )
        return ctx

class ChickenListView(ListView):
    model = Chicken
    template_name = "web_app/chicken_list.html"
    paginate_by = 50          # optional

    # -----------------------------------------------------------------
    # helper: translate ?sort= query-param to an ORM .order_by() clause
    # -----------------------------------------------------------------
    ORDER_MAP = {
        "name": "name",
        "-name": "-name",
        "dob": "date_of_birth",
        "-dob": "-date_of_birth",
        "dod": "date_of_death",
        "-dod": "-date_of_death",
        "eggs30": "eggs_per_day",
        "-eggs30": "-eggs_per_day",
        "eggstotal": "eggs_total",
        "-eggstotal": "-eggs_total",
        "lastegg": "last_egg",
        "-lastegg": "-last_egg",
    }

    def get_queryset(self):
        qs = (
            Chicken.objects.with_egg_metrics(30)
            .annotate(
                eggs_total=Count("egg"),
                last_egg=Max("egg__laid_at"),
            )
            .select_related()   # nothing to prefetch here but keeps pattern
        )

        sort_param = self.request.GET.get("sort", "name")
        qs = qs.order_by(sort_param)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sort"] = self.request.GET.get("sort", "name")
        ctx["headers"] = [
            ("name", "Name"),
            ("tag_string", "Tag"),
            ("date_of_birth", "DoB"),
            ("date_of_death", "DoD"),
            ("eggs_per_day", "Eggs/d (last 30 days)"),
            ("eggs_total", "Eggs total"),
            ("last_egg", "Last egg"),
        ]
        return ctx

class ChickenDetailView(DetailView):
    model = Chicken
    template_name = "web_app/chicken_detail.html"
    context_object_name = "hen"

    DAYS_BACK = 60           # how many days to plot

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hen = self.object

        # ------------------------------------------------------------
        # 1) Egg-per-day series + 10-day rolling mean
        # ------------------------------------------------------------
        today = date.today()
        start = today - timedelta(days=self.DAYS_BACK - 1)

        eggs = (
            Egg.objects
            .filter(chicken=hen, laid_at__date__gte=start)
            .values("laid_at__date")
            .annotate(cnt=Count("id"))
        )
        counts_by_day = {row["laid_at__date"]: row["cnt"] for row in eggs}

        labels, daily, rolling = [], [], []
        window = 10
        buf = []

        for i in range(self.DAYS_BACK):
            d = start + timedelta(days=i)
            labels.append(d.isoformat())
            c = counts_by_day.get(d, 0)
            daily.append(c)
            buf.append(c)
            if len(buf) > window:
                buf.pop(0)
            rolling.append(round(sum(buf) / len(buf), 2))

        ctx["chart_labels"] = json.dumps(labels)
        ctx["chart_daily"] = json.dumps(daily)
        ctx["chart_rolling"] = json.dumps(rolling)

        # ------------------------------------------------------------
        # 2) Nesting-box presence last 24 h
        # ------------------------------------------------------------
        now = timezone.localtime()
        since = now - timedelta(hours=24)
        presence = (
            NestingBoxPresence.objects
            .filter(chicken=hen, present_at__gte=since)
            .select_related("nesting_box")
            .order_by("present_at")
        )
        ctx["presence_events"] = presence

        # ------------------------------------------------------------
        # 3) Quick stats
        # ------------------------------------------------------------
        stats = (
            Egg.objects.filter(chicken=hen)
            .aggregate(
                total=Count("id"),
                last=Max("laid_at"),
                last30=Count("id", filter=Q(laid_at__gte=timezone.now() - timedelta(days=30))),
            )
        )
        ctx["stats"] = stats
        return ctx

class NestingBoxListView(TemplateView):
    pass

class EggAnalyticsView(TemplateView):
    pass