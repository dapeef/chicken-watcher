from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from ..models import Egg
from ..forms import EggForm


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
            ("quality", "Quality"),
        ]
        return ctx


class EggCreateView(CreateView):
    model = Egg
    form_class = EggForm
    template_name = "web_app/egg_form.html"
    success_url = reverse_lazy("egg_list")


class EggUpdateView(UpdateView):
    model = Egg
    form_class = EggForm
    template_name = "web_app/egg_form.html"
    success_url = reverse_lazy("egg_list")


class EggDeleteView(DeleteView):
    model = Egg
    template_name = "web_app/egg_confirm_delete.html"
    success_url = reverse_lazy("egg_list")
