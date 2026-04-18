from django import forms
from django.utils import timezone
from .models import Egg


class EggForm(forms.ModelForm):
    """
    Simple ModelForm so we can tweak the DateTime widget.
    """

    laid_at = forms.DateTimeField(
        initial=timezone.localtime,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    quality = forms.ChoiceField(
        choices=Egg.Quality.choices,
        initial=Egg.Quality.SALEABLE,
        required=False,
    )

    class Meta:
        model = Egg
        fields = ["chicken", "nesting_box", "laid_at", "quality"]

    # Keep DB value timezone-aware
    def clean_laid_at(self):
        value = self.cleaned_data["laid_at"]
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value

    def clean_quality(self):
        value = self.cleaned_data.get("quality") or Egg.Quality.SALEABLE
        return value
