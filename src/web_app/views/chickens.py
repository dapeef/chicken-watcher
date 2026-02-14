import json
from datetime import timedelta, date
from django.views.generic import ListView, DetailView
from django.db.models import Count, Max, Q
from django.utils import timezone

from ..models import Chicken, Egg, NestingBoxPresence
from ..utils import rolling_average

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
