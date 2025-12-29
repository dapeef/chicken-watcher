from django.utils import timezone
from django.views.generic import TemplateView
from .models import Egg, Chicken, NestingBoxPresence
from django.db.models import Count


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

class ChickenListView(TemplateView):
    pass

class NestingBoxListView(TemplateView):
    pass

class EggAnalyticsView(TemplateView):
    pass