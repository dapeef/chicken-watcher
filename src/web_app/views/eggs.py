from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from ..models import Egg
from ..forms import EggForm


class EggListView(ListView):
    model = Egg
    template_name = "web_app/egg_list.html"

    def get_queryset(self):
        # select_related avoids an N+1 over chicken and nesting_box on
        # the egg_list template (which prints {{ egg.chicken.name }} and
        # {{ egg.nesting_box.name }} for every row). Without it a page
        # showing 200 eggs runs ~401 queries; with it, 1.
        #
        # Pagination is still TODO — see Wave 4 / Wave 5 in
        # docs/tech-debt-review.md. Adding paginate_by without updating
        # the template would silently truncate the list.
        qs = Egg.objects.select_related("chicken", "nesting_box")

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
