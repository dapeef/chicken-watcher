import pytest
import json
import factory
from datetime import timedelta, date
from django.urls import reverse
from django.utils import timezone
from .factories import (
    ChickenFactory,
    EggFactory,
    HardwareSensorFactory,
    NestingBoxFactory,
    NestingBoxPresenceFactory,
    NestingBoxImageFactory,
)
from web_app.models import Egg


@pytest.mark.django_db
class TestViews:
    def test_dashboard_view(self, client):
        c1 = ChickenFactory(name="C1")
        b1 = NestingBoxFactory(name="Box1")
        NestingBoxFactory(name="Box2")

        # Create some presences today
        NestingBoxPresenceFactory(
            chicken=c1,
            nesting_box=b1,
            present_at=timezone.now() - timedelta(minutes=10),
        )
        p_latest = NestingBoxPresenceFactory(
            chicken=c1, nesting_box=b1, present_at=timezone.now() - timedelta(minutes=5)
        )

        url = reverse("dashboard")
        response = client.get(url)
        assert response.status_code == 200

        latest_presence = response.context["latest_presence"]
        # Should contain p_latest for b1
        assert p_latest in latest_presence
        # Should only have one entry for b1
        assert len([p for p in latest_presence if p.nesting_box == b1]) == 1

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

    def test_partial_sensors(self, client):
        HardwareSensorFactory(name="rfid_test", is_connected=True)
        url = reverse("partial_sensors")
        response = client.get(url)
        assert response.status_code == 200
        assert b"rfid_test" in response.content
        assert b"Online" in response.content

    def test_other_partials(self, client):
        partials = [
            "partial_eggs_today",
            "partial_laid_chickens",
            "partial_latest_image",
            "partial_latest_presence",
            "partial_latest_events",
        ]
        for p in partials:
            url = reverse(p)
            response = client.get(url)
            assert response.status_code == 200

    def test_timeline_view(self, client):
        url = reverse("timeline")
        response = client.get(url)
        assert response.status_code == 200

    def test_timeline_data(self, client):
        url = reverse("timeline_data")
        # Test without params
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == []

        # Test with params
        start = "2026-02-14T00:00:00Z"
        end = "2026-02-14T23:59:59Z"
        response = client.get(f"{url}?start={start}&end={end}")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

        # Test with naive strings
        start = "2026-02-14T00:00:00"
        end = "2026-02-14T23:59:59"
        response = client.get(f"{url}?start={start}&end={end}")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_partial_image_at_time(self, client):
        url = reverse("partial_image_at_time")
        response = client.get(url)
        assert response.status_code == 200

        response = client.get(url + "?t=2026-02-14T14:00:00")
        assert response.status_code == 200

    def test_timeline_images(self, client):
        from web_app.models import NestingBoxImage
        now = timezone.now()
        for i in range(5):
            NestingBoxImageFactory(created_at=now - timedelta(minutes=i * 10))
        
        assert NestingBoxImage.objects.count() == 5

        url = reverse("timeline_images")
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        # Test with sampling
        response = client.get(f"{url}?start={start}&end={end}&n=2")
        assert response.status_code == 200
        data = response.json()
        # Should return n=2 plus possibly the last one if it was sampled out,
        # our logic ensures at least n are returned if available.
        assert len(data) >= 2
        assert "url" in data[0]
        assert "timestamp" in data[0]

        # Test with more n than available
        response = client.get(f"{url}?start={start}&end={end}&n=10")
        assert len(response.json()) == 5
