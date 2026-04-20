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
        ChickenFactory(
            date_of_birth=start - timedelta(days=1),
            date_of_death=None,
        )
        ChickenFactory(
            date_of_birth=start - timedelta(days=1),
            date_of_death=today - timedelta(days=2),
        )

        url = reverse("metrics")
        response = client.get(
            url,
            {
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
        ChickenFactory(date_of_birth=today, date_of_death=None)

        url = reverse("metrics")
        response = client.get(
            url,
            {
                "start": (today - timedelta(days=2)).isoformat(),
                "end": today.isoformat(),
            },
        )
        flock = json.loads(response.context["flock_count_dataset_json"])
        data = flock["data"]

        assert data[0] == 0
        assert data[1] == 0
        assert data[-1] == 1

    def test_flock_count_ignores_chicken_selection(self, client):
        """The flock size chart always shows the full flock headcount,
        not just the selected chickens. This lets you compare a single
        hen's production against the actual population trend."""
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        dob = start - timedelta(days=1)
        c1 = ChickenFactory(date_of_birth=dob)
        ChickenFactory(date_of_birth=dob)
        ChickenFactory(date_of_birth=dob)

        url = reverse("metrics")
        # Only select c1 — the other two should still be counted in the flock.
        response = client.get(
            url,
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        flock = json.loads(response.context["flock_count_dataset_json"])
        data = flock["data"]

        # All three alive hens must appear even though only c1 was selected.
        assert all(v == 3 for v in data if v is not None), (
            f"Expected flock count of 3 throughout (all hens, not just selected), got {data}"
        )
