import pytest
from django.urls import reverse
from django.utils import timezone
from .factories import ChickenFactory, NestingBoxFactory, HardwareSensorFactory
from web_app.models import Egg

@pytest.mark.django_db
class TestE2E:
    """
    End-to-end style integration tests to verify that the application
    renders correctly and that multi-step processes work as expected.
    """

    def test_navigation_and_page_rendering(self, client):
        """
        Verify that all main pages are accessible and render their expected content.
        """
        # Set up some data to ensure things are rendered
        chicken = ChickenFactory(name="Bertha")
        HardwareSensorFactory(name="rfid_left", is_connected=True)
        
        # 1. Dashboard
        response = client.get(reverse("dashboard"))
        assert response.status_code == 200
        assert b"Today" in response.content
        assert b"rfid_left" in response.content
        assert b"Online" in response.content
        assert b"Sensors" in response.content

        # 2. Chickens List
        response = client.get(reverse("chicken_list"))
        assert response.status_code == 200
        assert b"Chickens" in response.content
        assert b"Bertha" in response.content
        assert b"Eggs/d" in response.content

        # 3. Chicken Detail
        response = client.get(reverse("chicken_detail", kwargs={"pk": chicken.pk}))
        assert response.status_code == 200
        assert b"Bertha" in response.content
        assert b"Production" in response.content
        assert b"Nesting behaviour" in response.content

        # 4. Egg List
        response = client.get(reverse("egg_list"))
        assert response.status_code == 200
        assert b"Eggs" in response.content
        assert b"Create new egg" in response.content

        # 5. Egg Production (Analytics)
        response = client.get(reverse("egg_production"))
        assert response.status_code == 200
        assert b"Egg Production" in response.content
        assert b"Rolling window" in response.content

    def test_egg_creation_workflow(self, client):
        """
        Test the complete process of creating a new egg via the web interface.
        """
        chicken = ChickenFactory(name="Alice")
        box = NestingBoxFactory(name="North Nest")
        
        # 1. Start at the Egg List and verify it's empty
        url_list = reverse("egg_list")
        response = client.get(url_list)
        assert b"Alice" not in response.content
        assert Egg.objects.count() == 0
        
        # 2. Find and click the 'Create new egg' link
        # (We simulate the 'click' by getting the URL from the response content 
        # or knowing it via reverse, and then visiting it)
        url_create = reverse("egg_create")
        response = client.get(url_create)
        assert response.status_code == 200
        assert b"Create Egg" in response.content or b"egg" in response.content.lower()
        
        # 3. Fill and submit the form
        now = timezone.localtime()
        data = {
            "chicken": chicken.pk,
            "nesting_box": box.pk,
            "laid_at": now.strftime("%Y-%m-%dT%H:%M"),
        }
        # follow=True simulates the redirect back to the list
        response = client.post(url_create, data, follow=True)
        
        # 4. Verify we are back on the list and the egg is there
        assert response.status_code == 200
        assert b"Alice" in response.content
        assert b"North Nest" in response.content
        
        # 5. Verify the record exists in the database
        assert Egg.objects.count() == 1
        new_egg = Egg.objects.first()
        assert new_egg.chicken == chicken
        assert new_egg.nesting_box == box

    def test_empty_states(self, client):
        """
        Verify that pages handle empty database states gracefully.
        """
        # Dashboard with no data
        response = client.get(reverse("dashboard"))
        assert response.status_code == 200
        assert b"0" in response.content # 0 eggs today
        
        # Chicken list empty
        response = client.get(reverse("chicken_list"))
        assert b"No chickens yet." in response.content

        # Egg list empty
        response = client.get(reverse("egg_list"))
        assert b"No eggs yet." in response.content
