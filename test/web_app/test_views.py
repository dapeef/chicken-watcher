import pytest
from django.urls import reverse
from .factories import ChickenFactory, EggFactory, HardwareSensorFactory

@pytest.mark.django_db
class TestViews:
    def test_dashboard_view(self, client):
        url = reverse("dashboard")
        response = client.get(url)
        assert response.status_code == 200
        assert "latest_presence" in response.context

    def test_chicken_list_view(self, client):
        ChickenFactory.create_batch(3)
        url = reverse("chicken_list")
        response = client.get(url)
        assert response.status_code == 200
        assert len(response.context["object_list"]) == 3

    def test_partial_sensors(self, client):
        HardwareSensorFactory(name="rfid_test", is_connected=True)
        url = reverse("partial_sensors")
        response = client.get(url)
        assert response.status_code == 200
        assert b"rfid_test" in response.content
        assert b"Online" in response.content

    def test_chicken_detail_view(self, client):
        chicken = ChickenFactory()
        url = reverse("chicken_detail", kwargs={"pk": chicken.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["hen"] == chicken
