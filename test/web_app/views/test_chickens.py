import pytest
import json
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
    NestingBoxPresencePeriodFactory,
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
        EggFactory.create_batch(
            5, chicken=chicken, laid_at=timezone.now() - timedelta(days=1)
        )

        url = reverse("chicken_detail", kwargs={"pk": chicken.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["hen"] == chicken
        assert response.context["stats"]["total"] == 5

        # Check chart data
        assert "chart_labels" in response.context
        assert "chart_daily" in response.context
        daily = json.loads(response.context["chart_daily"])
        assert sum(daily) == 5

    def test_chicken_timeline_data_returns_periods_and_eggs(self, client):
        chicken = ChickenFactory()
        box = NestingBoxFactory(name="left")
        now = timezone.now()

        period = NestingBoxPresencePeriodFactory(
            chicken=chicken,
            nesting_box=box,
            started_at=now - timedelta(minutes=30),
            ended_at=now - timedelta(minutes=10),
        )
        egg = EggFactory(
            chicken=chicken,
            nesting_box=box,
            laid_at=now - timedelta(minutes=15),
        )

        start = (now - timedelta(hours=1)).isoformat()
        end = now.isoformat()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url, {"start": start, "end": end})

        assert response.status_code == 200
        data = json.loads(response.content)
        ids = {item["id"] for item in data}
        assert f"period_{period.id}" in ids
        assert f"egg_{egg.id}" in ids

    def test_chicken_timeline_data_excludes_other_chickens(self, client):
        chicken = ChickenFactory()
        other = ChickenFactory()
        box = NestingBoxFactory(name="left")
        now = timezone.now()

        NestingBoxPresencePeriodFactory(
            chicken=other,
            nesting_box=box,
            started_at=now - timedelta(minutes=30),
            ended_at=now - timedelta(minutes=10),
        )

        start = (now - timedelta(hours=1)).isoformat()
        end = now.isoformat()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url, {"start": start, "end": end})

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data == []

    def test_chicken_timeline_data_missing_params_returns_empty(self, client):
        chicken = ChickenFactory()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert json.loads(response.content) == []

    def test_chicken_timeline_data_invalid_chicken_returns_404(self, client):
        url = reverse("chicken_timeline_data", kwargs={"pk": 99999})
        response = client.get(url)
        assert response.status_code == 404
