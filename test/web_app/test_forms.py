import pytest
from django.utils import timezone

from test.web_app.factories import ChickenFactory, NestingBoxFactory
from web_app.forms import EggForm


@pytest.mark.django_db
class TestEggForm:
    def test_valid_form(self):
        chicken = ChickenFactory()
        box = NestingBoxFactory()
        now = timezone.now().replace(second=0, microsecond=0)
        data = {
            "chicken": chicken.pk,
            "nesting_box": box.pk,
            "laid_at": now.strftime("%Y-%m-%dT%H:%M"),
        }
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()
        assert egg.chicken == chicken
        assert egg.nesting_box == box
        # Check that it's aware and close to what we sent
        assert timezone.is_aware(egg.laid_at)
        assert egg.laid_at.year == now.year
        assert egg.laid_at.month == now.month
        assert egg.laid_at.day == now.day

    def test_valid_form_quality_messy(self):
        now = timezone.now().replace(second=0, microsecond=0)
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": now.strftime("%Y-%m-%dT%H:%M"),
            "quality": "messy",
        }
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()
        assert egg.quality == "messy"

    def test_valid_form_quality_edible(self):
        now = timezone.now().replace(second=0, microsecond=0)
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": now.strftime("%Y-%m-%dT%H:%M"),
            "quality": "edible",
        }
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()
        assert egg.quality == "edible"

    def test_valid_form_quality_defaults_to_saleable(self):
        # Omitting 'quality' from POST data should use the model default
        now = timezone.now().replace(second=0, microsecond=0)
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": now.strftime("%Y-%m-%dT%H:%M"),
        }
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()
        assert egg.quality == "saleable"

    def test_invalid_quality_fails_validation(self):
        now = timezone.now().replace(second=0, microsecond=0)
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": now.strftime("%Y-%m-%dT%H:%M"),
            "quality": "bad_value",
        }
        form = EggForm(data=data)
        assert not form.is_valid()
        assert "quality" in form.errors

    def test_invalid_form(self):
        # laid_at is required in the form
        form = EggForm(data={"chicken": "", "nesting_box": "", "laid_at": ""})
        assert not form.is_valid()
        assert "laid_at" in form.errors
