"""Shared helpers for timeline data views."""

from datetime import datetime

from django.http import JsonResponse
from django.utils import timezone


def parse_date_range(request):
    """
    Parse ``start`` and ``end`` GET params as timezone-aware datetimes.

    Returns ``(start, end)`` on success, or raises ``ValueError`` if either
    param is missing or cannot be parsed.
    """
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    if not start_str or not end_str:
        raise ValueError("Missing start or end parameter")

    start = datetime.fromisoformat(start_str.replace("Z", "+00:00").replace(" ", "+"))
    if timezone.is_naive(start):
        start = timezone.make_aware(start)

    end = datetime.fromisoformat(end_str.replace("Z", "+00:00").replace(" ", "+"))
    if timezone.is_naive(end):
        end = timezone.make_aware(end)

    return start, end


def egg_item(egg, *, include_group=False):
    """Serialise an Egg instance as a vis-timeline item dict."""
    class_name = "timeline-egg timeline-egg--dud" if egg.dud else "timeline-egg"
    item = {
        "id": f"egg_{egg.id}",
        "content": "🥚",
        "start": egg.laid_at.isoformat(),
        "className": class_name,
    }
    if include_group:
        item["group"] = f"chicken_{egg.chicken_id}" if egg.chicken_id else "unknown"
    return item


def period_item(period, *, include_group=False):
    """Serialise a NestingBoxPresencePeriod instance as a vis-timeline item dict."""
    item = {
        "id": f"period_{period.id}",
        "content": f"📥 {period.nesting_box.name}",
        "start": period.started_at.isoformat(),
        "end": period.ended_at.isoformat(),
        "type": "range",
        "className": f"timeline-period box-{period.nesting_box.name}",
    }
    if include_group:
        item["group"] = f"chicken_{period.chicken_id}"
    return item


def presence_item(presence):
    """Serialise a NestingBoxPresence instance as a vis-timeline point item dict."""
    return {
        "id": f"presence_{presence.id}",
        "content": "",
        "start": presence.present_at.isoformat(),
        "type": "point",
        "className": f"timeline-presence-dot box-{presence.nesting_box.name}",
        "group": f"chicken_{presence.chicken_id}",
    }


def empty_range_response(request):
    """Shorthand JsonResponse for an empty list, used when params are missing/invalid."""
    return JsonResponse([], safe=False)
