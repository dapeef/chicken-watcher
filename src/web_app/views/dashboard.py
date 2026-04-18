"""
Dashboard and its HTMX-polled partials.

The dashboard has six live-updating panels (eggs today, laid chickens,
latest presence, latest events, sensor status, latest image). Each
polls its own partial every few seconds via HTMX.

Previously every partial view called a monolithic ``get_dashboard_context()``
that ran *all seven* queries (one per panel + today-start setup). With
six panels polling every 5 seconds, that was 42 queries every 5 s just
for the idle dashboard. Now each partial fetches only what it needs,
so the same idle dashboard does ~6 queries per cycle.

The :class:`DashboardView` first render still calls every fetcher once
(the initial HTML needs all the data), but subsequent refreshes are
per-partial.
"""

from django import db
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from ..models import (
    Chicken,
    Egg,
    HardwareSensor,
    NestingBoxImage,
    NestingBoxPresencePeriod,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _today_start():
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Per-panel data fetchers — each returns a small dict for its own partial.
# ---------------------------------------------------------------------------


def _eggs_today_ctx() -> dict:
    today_start = _today_start()
    return {
        "eggs_today": Egg.objects.filter(
            laid_at__range=(today_start, timezone.localtime())
        ).count()
    }


def _laid_chickens_ctx() -> dict:
    today_start = _today_start()
    eggs_today = Egg.objects.filter(laid_at__range=(today_start, timezone.localtime()))
    return {"laid_chickens": Chicken.objects.filter(egg__in=eggs_today).distinct()}


def _latest_presence_ctx() -> dict:
    today_start = _today_start()

    # PostgreSQL path: single DISTINCT ON query.
    if db.connection.vendor == "postgresql":
        latest_presence = (
            NestingBoxPresencePeriod.objects.filter(ended_at__gte=today_start)
            .select_related("chicken", "nesting_box")
            .order_by("nesting_box_id", "-ended_at")
            .distinct("nesting_box_id")
        )
    else:
        # SQLite fallback: one query per active box. ``order_by()``
        # clears the default Meta.ordering before distinct(), otherwise
        # Django silently adds the ordering columns to the SELECT list
        # and distinct becomes a no-op.
        latest_presence = []
        box_ids = (
            NestingBoxPresencePeriod.objects.filter(ended_at__gte=today_start)
            .order_by()
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
    return {"latest_presence": latest_presence}


def _latest_events_ctx() -> dict:
    today_start = _today_start()
    return {
        "latest_events": Egg.objects.filter(laid_at__gte=today_start)
        .select_related("chicken", "nesting_box")
        .order_by("-laid_at")[:10]
    }


def _sensors_ctx() -> dict:
    return {"sensors": HardwareSensor.objects.all()}


def _latest_image_ctx() -> dict:
    return {"latest_image": NestingBoxImage.objects.first()}


def get_dashboard_context() -> dict:
    """Aggregate all per-panel contexts for the initial full-page render.

    Runs every fetcher in sequence, so the initial dashboard load fires
    a query for each panel. Subsequent HTMX refreshes only fetch the
    panel that's polling — that's the whole point of the per-partial
    split.

    Kept public because the integration tests in
    ``test/web_app/test_timezone.py`` assert on the full context dict
    directly.
    """
    ctx = {}
    for fetcher in (
        _eggs_today_ctx,
        _laid_chickens_ctx,
        _latest_presence_ctx,
        _latest_events_ctx,
        _sensors_ctx,
        _latest_image_ctx,
    ):
        ctx.update(fetcher())
    return ctx


# ---------------------------------------------------------------------------
# Full-page view
# ---------------------------------------------------------------------------


class DashboardView(TemplateView):
    template_name = "web_app/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(get_dashboard_context())
        # Consumed by dashboard_image.js via json_script.
        ctx["dashboard_config"] = {
            "latest_image_url": reverse("partial_latest_image"),
        }
        # URLs for the htmx_poll_panel inclusion tag. Kept here rather
        # than hard-coded in the template so the URL names remain
        # refactorable from one place.
        ctx["partial_eggs_today_url"] = reverse("partial_eggs_today")
        ctx["partial_laid_chickens_url"] = reverse("partial_laid_chickens")
        ctx["partial_latest_presence_url"] = reverse("partial_latest_presence")
        ctx["partial_latest_events_url"] = reverse("partial_latest_events")
        ctx["partial_sensors_url"] = reverse("partial_sensors")
        return ctx


# ---------------------------------------------------------------------------
# Per-panel partial views (HTMX polling targets)
# ---------------------------------------------------------------------------


def partial_eggs_today(request):
    return render(request, "web_app/partials/_eggs_today.html", _eggs_today_ctx())


def partial_laid_chickens(request):
    return render(request, "web_app/partials/_laid_chickens.html", _laid_chickens_ctx())


def partial_sensors(request):
    return render(request, "web_app/partials/_sensors.html", _sensors_ctx())


def partial_latest_image(request):
    return render(request, "web_app/partials/_latest_image.html", _latest_image_ctx())


def partial_latest_presence(request):
    return render(
        request, "web_app/partials/_latest_presence.html", _latest_presence_ctx()
    )


def partial_latest_events(request):
    return render(request, "web_app/partials/_latest_events.html", _latest_events_ctx())
