from django import forms
from django.utils import timezone

from .models import Egg


class EggForm(forms.ModelForm):
    """
    ModelForm for the Egg add/edit page.

    Each field's widget has its Bootstrap classes pre-set so the
    template can render fields with a plain
    ``<label>{{ field.label }}</label>{{ field }}`` pattern rather
    than hand-rolling every ``<input>`` / ``<select>`` tag.
    """

    laid_at = forms.DateTimeField(
        initial=timezone.localtime,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    quality = forms.ChoiceField(
        choices=Egg.Quality.choices,
        initial=Egg.Quality.SALEABLE,
        required=False,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = Egg
        fields = ["chicken", "nesting_box", "laid_at", "quality"]
        widgets = {
            "chicken": forms.Select(attrs={"class": "form-select"}),
            "nesting_box": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "chicken": "Chicken",
            "nesting_box": "Nesting box",
            "laid_at": "Laid at",
            "quality": "Quality",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Empty-choice labels for the two optional FKs. The Meta
        # ``blank=True`` on the model already makes them optional, but
        # the dropdown shows the unhelpful default "---------" unless
        # we override empty_label.
        if "chicken" in self.fields:
            self.fields["chicken"].empty_label = "— Unknown —"
        if "nesting_box" in self.fields:
            self.fields["nesting_box"].empty_label = "— Unknown —"

    # Keep DB value timezone-aware
    def clean_laid_at(self):
        value = self.cleaned_data["laid_at"]
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean_quality(self):
        value = self.cleaned_data.get("quality") or Egg.Quality.SALEABLE
        return value
