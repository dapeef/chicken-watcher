from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from ..models import Egg
from ..forms import EggForm


class EggListView(ListView):
    model = Egg
    template_name = "web_app/egg_list.html"
    paginate_by = 50  # 50 rows/page is comfortable on the Pi and phones

    def get_queryset(self):
        # select_related avoids an N+1 over chicken and nesting_box on
        # the egg_list template (which prints {{ egg.chicken.name }} and
        # {{ egg.nesting_box.name }} for every row). Without it a page
        # showing 200 eggs runs ~401 queries; with it, 1.
        qs = Egg.objects.select_related("chicken", "nesting_box")

        sort_param = self.request.GET.get("sort", "-laid_at")
        qs = qs.order_by(sort_param)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sort"] = self.request.GET.get("sort", "-laid_at")
        # (col_key, label, show_on_mobile). The sort_header tag in
        # chicken_extras consumes this tuple shape; keeping it
        # consistent across the list pages lets us share the tag.
        ctx["headers"] = [
            ("chicken", "Chicken", True),
            ("nesting_box", "Nesting box", True),
            ("laid_at", "Laid at", False),
            ("quality", "Quality", False),
        ]
        # For the _pagination.html partial — preserve all query-string
        # params across page links EXCEPT ``page`` (which gets replaced
        # per link). Using .copy() produces a QueryDict we can mutate.
        qs = self.request.GET.copy()
        qs.pop("page", None)
        ctx["querystring_without_page"] = qs.urlencode()
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
