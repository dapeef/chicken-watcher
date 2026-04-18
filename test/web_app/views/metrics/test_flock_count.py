import json
from datetime import timedelta

import pytest
from django.urls import reverse

from test.web_app.factories import ChickenFactory


@pytest.mark.django_db
class TestMetricsViewFlockCount:
    def test_flock_count_reflects_alive_chickens_only(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=4)
        c1 = ChickenFactory(
            date_of_birth=start - timedelta(days=1),
            date_of_death=None,
        )
        c2 = ChickenFactory(
            date_of_birth=start - timedelta(days=1),
            date_of_death=today - timedelta(days=2),
        )

        url = reverse("metrics")
        response = client.get(
            url,
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk), str(c2.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        flock = json.loads(response.context["flock_count_dataset_json"])
        data = flock["data"]

        assert data[0] == 2
        assert data[-1] == 1

    def test_flock_count_zero_before_any_dob(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        c1 = ChickenFactory(date_of_birth=today, date_of_death=None)

        url = reverse("metrics")
        response = client.get(
            url,
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk)],
                "start": (today - timedelta(days=2)).isoformat(),
                "end": today.isoformat(),
            },
        )
        flock = json.loads(response.context["flock_count_dataset_json"])
        data = flock["data"]

        assert data[0] == 0
        assert data[1] == 0
        assert data[-1] == 1
