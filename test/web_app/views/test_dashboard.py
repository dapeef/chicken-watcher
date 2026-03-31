import pytest
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from ..factories import (
    ChickenFactory,
    HardwareSensorFactory,
    NestingBoxFactory,
    NestingBoxPresenceFactory,
)


@pytest.mark.django_db
class TestDashboardViews:
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
