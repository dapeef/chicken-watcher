import pytest
import json
from datetime import timedelta, date
from django.urls import reverse
from django.utils import timezone
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
)
from web_app.models import Egg


@pytest.mark.django_db
class TestEggViews:
    def test_egg_production_view_dob_dod_filtering(self, client):
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Chicken born today
        c1 = ChickenFactory(name="BornToday", date_of_birth=today)
        # Egg "yesterday" (impossible but in DB)
        EggFactory(chicken=c1, laid_at=timezone.now() - timedelta(days=1))
        # Egg today
        EggFactory(chicken=c1, laid_at=timezone.now())

        url = reverse("egg_production")
        # Use window=1 to see raw counts after DOB filtering
        response = client.get(
            url + f"?start={yesterday.isoformat()}&end={today.isoformat()}&w=1"
        )
        datasets = json.loads(response.context["datasets_json"])

        # datasets[0] should be for BornToday
        # labels are [yesterday, today]
        # counts should be [None, 1]
        data = datasets[0]["data"]
        assert data[0] is None
        assert data[1] == 1

        # Test DOD filtering
        c2 = ChickenFactory(
            name="DiedYesterday",
            date_of_birth=yesterday - timedelta(days=10),
            date_of_death=yesterday,
        )
        # Egg today (recorded after death)
        EggFactory(chicken=c2, laid_at=timezone.now())

        response = client.get(
            url + f"?start={yesterday.isoformat()}&end={today.isoformat()}&w=1"
        )
        datasets = json.loads(response.context["datasets_json"])

        # Find c2 dataset
        c2_data = next(d["data"] for d in datasets if d["label"] == "DiedYesterday")
        # labels: [yesterday, today]
        # yesterday: 0 (within life)
        # today: None (after death)
        assert c2_data[0] == 0
        assert c2_data[1] is None

    def test_egg_list_view(self, client):
        c1 = ChickenFactory(name="C1")
        c2 = ChickenFactory(name="C2")
        EggFactory(chicken=c1, laid_at=timezone.now() - timedelta(hours=1))
        EggFactory(chicken=c2, laid_at=timezone.now())

        url = reverse("egg_list")
        response = client.get(url)
        assert response.status_code == 200
        eggs = response.context["object_list"]
        assert len(eggs) == 2
        # Default sort is -laid_at
        assert eggs[0].chicken == c2
        assert eggs[1].chicken == c1

    def test_egg_create_view(self, client):
        chicken = ChickenFactory()
        box = NestingBoxFactory()
        url = reverse("egg_create")

        # GET
        response = client.get(url)
        assert response.status_code == 200

        # POST valid
        data = {
            "chicken": chicken.pk,
            "nesting_box": box.pk,
            "laid_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert Egg.objects.count() == 1

    def test_egg_production_view(self, client):
        chicken = ChickenFactory()
        EggFactory(chicken=chicken, laid_at=timezone.now())

        url = reverse("egg_production")
        response = client.get(url)
        assert response.status_code == 200
        assert "datasets_json" in response.context
        datasets = json.loads(response.context["datasets_json"])
        assert len(datasets) == 1
        assert datasets[0]["label"] == chicken.name

    def test_egg_production_view_filters(self, client):
        chicken = ChickenFactory()
        # One egg today
        EggFactory(chicken=chicken, laid_at=timezone.now())
        # One egg 10 days ago
        EggFactory(chicken=chicken, laid_at=timezone.now() - timedelta(days=10))

        url = reverse("egg_production")
        # Test window parameter
        response = client.get(url + "?w=7")
        assert response.status_code == 200
        assert response.context["window"] == 7

        # Test invalid window (should fallback to 30)
        response = client.get(url + "?w=5")
        assert response.context["window"] == 30

        # Test date range
        today = date.today()
        yesterday = today - timedelta(days=1)
        response = client.get(
            url + f"?start={yesterday.isoformat()}&end={today.isoformat()}"
        )
        assert response.status_code == 200
        assert response.context["start"] == yesterday.isoformat()
        assert response.context["end"] == today.isoformat()
