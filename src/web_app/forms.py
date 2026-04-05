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

    class Meta:
        model = Egg
        fields = ["chicken", "nesting_box", "laid_at", "dud"]

    # Keep DB value timezone-aware
    def clean_laid_at(self):
        value = self.cleaned_data["laid_at"]
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return value
