import pytest
from datetime import timedelta
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

    def test_egg_delete_view_get_shows_confirmation(self, client):
        egg = EggFactory()
        url = reverse("egg_delete", args=[egg.pk])

        response = client.get(url)
        assert response.status_code == 200
        assert "Are you sure" in response.content.decode()

    def test_egg_delete_view_post_deletes_egg(self, client):
        egg = EggFactory()
        url = reverse("egg_delete", args=[egg.pk])

        response = client.post(url)
        assert response.status_code == 302
        assert Egg.objects.count() == 0

    def test_egg_delete_view_redirects_to_egg_list(self, client):
        egg = EggFactory()
        url = reverse("egg_delete", args=[egg.pk])

        response = client.post(url)
        assert response.url == reverse("egg_list")

    def test_egg_delete_view_nonexistent_egg_returns_404(self, client):
        url = reverse("egg_delete", args=[9999])

        response = client.get(url)
        assert response.status_code == 404

    def test_egg_create_view_messy_quality(self, client):
        url = reverse("egg_create")
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "quality": "messy",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert Egg.objects.filter(quality="messy").count() == 1

    def test_egg_create_view_quality_defaults_to_saleable(self, client):
        url = reverse("egg_create")
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert Egg.objects.filter(quality="saleable").count() == 1

    def test_egg_list_shows_quality_column(self, client):
        EggFactory(quality="messy")
        EggFactory(quality="saleable")
        EggFactory(quality="edible")
        url = reverse("egg_list")
        response = client.get(url)
        content = response.content.decode()
        assert "Quality" in content
        assert "Messy" in content
        assert "Saleable" in content
        assert "Edible" in content
