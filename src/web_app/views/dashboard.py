from django import db
from django.utils import timezone
from django.views.generic import TemplateView
from django.shortcuts import render

from ..models import (
    Egg,
    Chicken,
    NestingBoxPresence,
    NestingBoxPresencePeriod,
    HardwareSensor,
    NestingBoxImage,
)


def get_dashboard_context():
    today_start = timezone.localtime().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    now = timezone.localtime()

    eggs_today_qs = Egg.objects.filter(laid_at__range=(today_start, now))

    # Latest presence period for each box
    if db.connection.vendor == "postgresql":
        latest_presence = (
            NestingBoxPresencePeriod.objects.filter(ended_at__gte=today_start)
            .select_related("chicken", "nesting_box")
            .order_by("nesting_box_id", "-ended_at")
            .distinct("nesting_box_id")
        )
    else:
        # Fallback for SQLite: pick the most recent period per box
        latest_presence = []
        box_ids = (
            NestingBoxPresencePeriod.objects.filter(ended_at__gte=today_start)
            .values_list("nesting_box_id", flat=True)
            .distinct()
        )
        for b_id in box_ids:
            p = (
                NestingBoxPresencePeriod.objects.filter(
                    nesting_box_id=b_id, ended_at__gte=today_start
                )
                .select_related("chicken", "nesting_box")
                .order_by("-ended_at")
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
