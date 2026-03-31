from datetime import datetime, timedelta
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import TemplateView

from ..models import (
    Chicken,
    Egg,
    NestingBoxPresence,
    NestingBoxImage,
    NestingBoxPresencePeriod,
)


class TimelineView(TemplateView):
    template_name = "web_app/timeline.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["chickens"] = Chicken.objects.all()
        return context


def timeline_data(request):
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    if not start_str or not end_str:
        return JsonResponse([], safe=False)

    try:
        start = datetime.fromisoformat(
            start_str.replace("Z", "+00:00").replace(" ", "+")
        )
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00").replace(" ", "+"))
        if timezone.is_naive(end):
            end = timezone.make_aware(end)
    except (ValueError, TypeError, OverflowError):
        return JsonResponse([], safe=False)

    eggs = Egg.objects.filter(laid_at__range=(start, end)).select_related(
        "chicken", "nesting_box"
    )

    if end - start <= timedelta(minutes=3):
        presences = NestingBoxPresence.objects.filter(
            present_at__range=(start, end)
        ).select_related("chicken", "nesting_box")
    else:
        presences = NestingBoxPresence.objects.none()

    periods = NestingBoxPresencePeriod.objects.filter(
        started_at__lte=end, ended_at__gte=start
    ).select_related("chicken", "nesting_box")

    timeline_items = []

    for egg in eggs:
        timeline_items.append(
            {
                "id": f"egg_{egg.id}",
                "content": "🥚",
                "start": egg.laid_at.isoformat(),
                "className": "timeline-egg",
                "group": f"chicken_{egg.chicken_id}" if egg.chicken_id else "unknown",
            }
        )

    for period in periods:
        timeline_items.append(
            {
                "id": f"period_{period.id}",
                "content": f"📥 {period.nesting_box.name}",
                "start": period.started_at.isoformat(),
                "end": period.ended_at.isoformat(),
                "type": "range",
                "className": f"timeline-period box-{period.nesting_box.name}",
                "group": f"chicken_{period.chicken_id}",
            }
        )

    for p in presences:
        timeline_items.append(
            {
                "id": f"presence_{p.id}",
                "content": "",
                "start": p.present_at.isoformat(),
                "type": "point",
                "className": f"timeline-presence-dot box-{p.nesting_box.name}",
                "group": f"chicken_{p.chicken_id}",
            }
        )

    return JsonResponse(timeline_items, safe=False)


def timeline_images(request):
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")
    try:
        n = int(request.GET.get("n", 100))
        if n < 1:
            n = 1
    except (ValueError, TypeError):
        n = 100

    if not start_str or not end_str:
        return JsonResponse([], safe=False)

    try:
        # Handle space instead of + from URL decoding
        start = datetime.fromisoformat(
            start_str.replace("Z", "+00:00").replace(" ", "+")
        )
        if timezone.is_naive(start):
            start = timezone.make_aware(start)
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00").replace(" ", "+"))
        if timezone.is_naive(end):
            end = timezone.make_aware(end)
    except (ValueError, TypeError, OverflowError):
        return JsonResponse([], safe=False)

    images_qs = NestingBoxImage.objects.filter(created_at__range=(start, end)).order_by(
        "created_at"
    )
    total_count = images_qs.count()

    if total_count == 0:
        return JsonResponse([], safe=False)

    if total_count <= n:
        images = images_qs
    else:
        # Sample n images evenly by index
        # Fetching all IDs is relatively cheap
        all_ids = list(images_qs.values_list("id", flat=True))
        step = len(all_ids) / n
        sampled_ids = [all_ids[int(i * step)] for i in range(n)]
        # Add the last one to ensure we cover the end of the range
        if all_ids[-1] not in sampled_ids:
            sampled_ids.append(all_ids[-1])
        images = NestingBoxImage.objects.filter(id__in=sampled_ids).order_by(
            "created_at"
        )

    data = [
        {"timestamp": img.created_at.isoformat(), "url": img.image.url}
        for img in images
    ]
    return JsonResponse(data, safe=False)


def partial_image_at_time(request):
    t_str = request.GET.get("t")
    if not t_str:
        return render(
            request, "web_app/partials/_latest_image.html", {"latest_image": None}
        )

    try:
        # Vis.js sends ISO strings, but let's be flexible
        target_time = datetime.fromisoformat(
            t_str.replace("Z", "+00:00").replace(" ", "+")
        )
        if timezone.is_naive(target_time):
            target_time = timezone.make_aware(target_time)
    except (ValueError, OverflowError):
        return render(
            request, "web_app/partials/_latest_image.html", {"latest_image": None}
        )

    # Find the image closest to this time
    # For simplicity, we find the latest image created BEFORE or AT this time
    closest_image = (
        NestingBoxImage.objects.filter(created_at__lte=target_time)
        .order_by("-created_at")
        .first()
    )

    # If none before, maybe one just after?
    if not closest_image:
        closest_image = (
            NestingBoxImage.objects.filter(created_at__gte=target_time)
            .order_by("created_at")
            .first()
        )

    return render(
        request, "web_app/partials/_latest_image.html", {"latest_image": closest_image}
    )
