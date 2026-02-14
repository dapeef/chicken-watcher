import pytest
from django.utils import timezone
from web_app.forms import EggForm
from test.web_app.factories import ChickenFactory, NestingBoxFactory


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

    def test_invalid_form(self):
        # laid_at is required in the form
        form = EggForm(data={"chicken": "", "nesting_box": "", "laid_at": ""})
        assert not form.is_valid()
        assert "laid_at" in form.errors
