import json
from datetime import timedelta, date, datetime
from django.urls import reverse_lazy
from django.views.generic import ListView, TemplateView, CreateView, DeleteView
from django.db.models import Count

from ..models import Egg, Chicken
from ..forms import EggForm
from ..utils import rolling_average, RIGHT


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


class EggDeleteView(DeleteView):
    model = Egg
    template_name = "web_app/egg_confirm_delete.html"
    success_url = reverse_lazy("egg_list")
