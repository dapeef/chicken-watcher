import pytest
import json
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxPresenceFactory,
)

@pytest.mark.django_db
class TestChickenViews:
    def test_chicken_list_view(self, client):
        ChickenFactory(name="Bertha")
        ChickenFactory(name="Alice")
        url = reverse("chicken_list")

        # Test default sorting (name)
        response = client.get(url)
        assert response.status_code == 200
        chickens = response.context["object_list"]
        assert len(chickens) == 2
        assert chickens[0].name == "Alice"
        assert chickens[1].name == "Bertha"

        # Test explicit sorting
        response = client.get(url + "?sort=-name")
        chickens = response.context["object_list"]
        assert chickens[0].name == "Bertha"
        assert chickens[1].name == "Alice"

    def test_chicken_detail_view(self, client):
        chicken = ChickenFactory()
        # Add some eggs to test stats and charts
        EggFactory.create_batch(
            5, chicken=chicken, laid_at=timezone.now() - timedelta(days=1)
        )
        NestingBoxPresenceFactory(
            chicken=chicken, present_at=timezone.now() - timedelta(minutes=5)
        )

        url = reverse("chicken_detail", kwargs={"pk": chicken.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["hen"] == chicken
        assert response.context["stats"]["total"] == 5
        assert len(response.context["presence_events"]) == 1

        # Check chart data
        assert "chart_labels" in response.context
        assert "chart_daily" in response.context
        daily = json.loads(response.context["chart_daily"])
        assert sum(daily) == 5
