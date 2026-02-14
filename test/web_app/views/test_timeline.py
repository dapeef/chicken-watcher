import pytest
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from ..factories import (
    EggFactory,
    NestingBoxPresenceFactory,
    NestingBoxImageFactory,
)

@pytest.mark.django_db
class TestTimelineViews:
    def test_timeline_view(self, client):
        url = reverse("timeline")
        response = client.get(url)
        assert response.status_code == 200

    def test_timeline_data(self, client):
        url = reverse("timeline_data")
        
        # Create some data
        now = timezone.now()
        egg = EggFactory(laid_at=now)
        presence = NestingBoxPresenceFactory(present_at=now)

        # Test without params
        response = client.get(url)
        assert response.status_code == 200
        assert response.json() == []

        # Test with range covering now
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()
        response = client.get(f"{url}?start={start}&end={end}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        
        ids = [item["id"] for item in data]
        assert f"egg_{egg.id}" in ids
        assert f"presence_{presence.id}" in ids

        # Test with range NOT covering now
        start = (now - timedelta(hours=5)).isoformat()
        end = (now - timedelta(hours=4)).isoformat()
        response = client.get(f"{url}?start={start}&end={end}")
        assert response.json() == []

    def test_timeline_data_invalid_dates(self, client):
        url = reverse("timeline_data")
        response = client.get(f"{url}?start=not-a-date&end=2026-02-14")
        assert response.status_code == 200
        assert response.json() == []

    def test_timeline_images_edge_cases(self, client):
        now = timezone.now()
        NestingBoxImageFactory(created_at=now)
        url = reverse("timeline_images")
        start = (now - timedelta(hours=1)).isoformat()
        end = (now + timedelta(hours=1)).isoformat()

        # n=1
        response = client.get(f"{url}?start={start}&end={end}&n=1")
        assert len(response.json()) == 1

        # invalid n
        response = client.get(f"{url}?start={start}&end={end}&n=abc")
        assert response.status_code == 200
        assert len(response.json()) == 1  # Should default to 100, but we only have 1 image

        # n=0 should be treated as n=1
        response = client.get(f"{url}?start={start}&end={end}&n=0")
        assert len(response.json()) == 1

    def test_partial_image_at_time_scenarios(self, client):
        t1 = timezone.now() - timedelta(minutes=20)
        t2 = timezone.now() - timedelta(minutes=10)
        img1 = NestingBoxImageFactory(created_at=t1)
        img2 = NestingBoxImageFactory(created_at=t2)

        url = reverse("partial_image_at_time")

        # 1. Target exactly at t1
        response = client.get(f"{url}?t={t1.isoformat()}")
        assert response.context["latest_image"] == img1

        # 2. Target between t1 and t2 (should pick img1 as it's the latest BEFORE or AT)
        t_mid = t1 + timedelta(minutes=5)
        response = client.get(f"{url}?t={t_mid.isoformat()}")
        assert response.context["latest_image"] == img1

        # 3. Target before t1 (should pick img1 because it's the closest after if none before)
        t_before = t1 - timedelta(minutes=5)
        response = client.get(f"{url}?t={t_before.isoformat()}")
        assert response.context["latest_image"] == img1

        # 4. Target after t2
        t_after = t2 + timedelta(minutes=5)
        response = client.get(f"{url}?t={t_after.isoformat()}")
        assert response.context["latest_image"] == img2
