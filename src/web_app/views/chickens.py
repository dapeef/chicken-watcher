from datetime import timedelta

from django.db.models import (
    Count,
    DateField,
    DurationField,
    ExpressionWrapper,
    F,
    Max,
    Q,
)
from django.db.models.functions import Cast, Coalesce, Now
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView

from ..models import Chicken, Egg, NestingBoxPresencePeriod
from .timeline_utils import (
    egg_item,
    empty_range_response,
    night_periods,
    parse_date_range,
    period_item,
)


class ChickenListView(ListView):
    model = Chicken
    template_name = "web_app/chicken_list.html"

    def get_queryset(self):
        # age_duration: (date_of_death ?? today) - date_of_birth as a timedelta.
        # date_of_death is already a DateField; Cast(Now(), DateField()) gives
        # today's date without requiring TruncDate (which only works on DateTimeFields).
        end_date = Coalesce(F("date_of_death"), Cast(Now(), output_field=DateField()))
        qs = Chicken.objects.annotate(
            eggs_total=Count("egg"),
            last_egg=Max("egg__laid_at"),
            age_duration=ExpressionWrapper(
                end_date - F("date_of_birth"),
                output_field=DurationField(),
            ),
        ).select_related("tag")

        sort_param = self.request.GET.get("sort", "name")
        qs = qs.order_by(sort_param)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sort"] = self.request.GET.get("sort", "name")
        # Tuples: (sort_key, label, show_on_mobile)
        ctx["headers"] = [
            ("name", "Name", True),
            ("age_duration", "Age", True),
            ("tag__number", "Tag number", True),
            ("eggs_total", "Eggs total", False),
            ("last_egg", "Last egg", False),
            ("date_of_birth", "DoB", False),
            ("date_of_death", "DoD", False),
        ]
        return ctx


class ChickenDetailView(DetailView):
    model = Chicken
    template_name = "web_app/chicken_detail.html"
    context_object_name = "hen"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        chicken = self.object

        stats = Egg.objects.filter(chicken=chicken).aggregate(
            total=Count("id"),
            last=Max("laid_at"),
            last30=Count(
                "id", filter=Q(laid_at__gte=timezone.now() - timedelta(days=30))
            ),
        )
        ctx["stats"] = stats
        # Consumed by chicken_detail.js via json_script (no XSS surface).
        ctx["chicken_detail_config"] = {
            "timeline_url": reverse("chicken_timeline_data", kwargs={"pk": chicken.pk}),
        }
        return ctx


def chicken_timeline_data(request, pk):
    chicken = get_object_or_404(Chicken, pk=pk)

    try:
        start, end = parse_date_range(request)
    except (ValueError, TypeError, OverflowError):
        return empty_range_response(request)

    eggs = Egg.objects.filter(
        chicken=chicken, laid_at__range=(start, end)
    ).select_related("nesting_box")

    periods = NestingBoxPresencePeriod.objects.filter(
        chicken=chicken, started_at__lte=end, ended_at__gte=start
    ).select_related("nesting_box")

    items = (
        night_periods(start, end)
        + [egg_item(e) for e in eggs]
        + [period_item(p) for p in periods]
    )

    return JsonResponse(items, safe=False)
