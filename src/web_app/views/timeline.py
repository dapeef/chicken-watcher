from datetime import timedelta
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
from .timeline_utils import (
    parse_date_range,
    egg_item,
    period_item,
    presence_item,
    empty_range_response,
)


class TimelineView(TemplateView):
    template_name = "web_app/timeline.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["chickens"] = Chicken.objects.all()
        return context


def timeline_data(request):
    try:
        start, end = parse_date_range(request)
    except (ValueError, TypeError, OverflowError):
        return empty_range_response(request)

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

    items = (
        [egg_item(e, include_group=True) for e in eggs]
        + [period_item(p, include_group=True) for p in periods]
        + [presence_item(p) for p in presences]
    )

    return JsonResponse(items, safe=False)


def timeline_images(request):
    try:
        n = int(request.GET.get("n", 100))
        if n < 1:
            n = 1
    except (ValueError, TypeError):
        n = 100

    try:
        start, end = parse_date_range(request)
    except (ValueError, TypeError, OverflowError):
        return empty_range_response(request)

    images_qs = NestingBoxImage.objects.filter(created_at__range=(start, end)).order_by(
        "created_at"
    )
    total_count = images_qs.count()

    if total_count == 0:
        return empty_range_response(request)

    if total_count <= n:
        images = images_qs
    else:
        # Sample n images evenly by index
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
        from datetime import datetime

        target_time = datetime.fromisoformat(
            t_str.replace("Z", "+00:00").replace(" ", "+")
        )
        if timezone.is_naive(target_time):
            target_time = timezone.make_aware(target_time)
    except (ValueError, OverflowError):
        return render(
            request, "web_app/partials/_latest_image.html", {"latest_image": None}
        )

    # Find the latest image created BEFORE or AT this time
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
