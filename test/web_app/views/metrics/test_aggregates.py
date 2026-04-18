import json
import pytest
from datetime import timedelta, datetime, timezone as dt_timezone
from django.urls import reverse

from test.web_app.factories import ChickenFactory, EggFactory


@pytest.mark.django_db
class TestMetricsViewAggregates:
    def test_show_sum_adds_sum_dataset_to_egg_prod(self, client):
        ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1", "show_sum": "1"})
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        assert any(d["label"] == "Sum" for d in datasets)

    def test_show_mean_adds_mean_dataset_to_egg_prod(self, client):
        ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1", "show_mean": "1"})
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        assert any(d["label"] == "Mean" for d in datasets)

    def test_show_sum_adds_sum_to_tod_egg(self, client):
        ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1", "show_sum": "1"})
        datasets = json.loads(response.context["tod_egg_datasets_json"])
        assert any(d["label"] == "Sum" for d in datasets)

    def test_show_sum_adds_sum_to_tod_nest(self, client):
        ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1", "show_sum": "1"})
        datasets = json.loads(response.context["tod_nest_datasets_json"])
        assert any(d["label"] == "Sum" for d in datasets)

    def test_no_aggregates_no_sum_or_mean(self, client):
        ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1"})
        for key in (
            "egg_prod_datasets_json",
            "tod_egg_datasets_json",
            "tod_nest_datasets_json",
        ):
            datasets = json.loads(response.context[key])
            labels = {d["label"] for d in datasets}
            assert "Sum" not in labels
            assert "Mean" not in labels

    def test_sum_values_equal_sum_of_individual_hens(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(2, chicken=c1, laid_at=today_dt)
        EggFactory.create_batch(3, chicken=c2, laid_at=today_dt)

        url = reverse("metrics")
        response = client.get(
            url,
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk), str(c2.pk)],
                "show_sum": "1",
                "start": start.isoformat(),
                "end": today.isoformat(),
                "w": "1",
            },
        )
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        sum_data = next(d["data"] for d in datasets if d["label"] == "Sum")
        assert sum_data[-1] == 5

    def test_mean_values_equal_sum_divided_by_n(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(2, chicken=c1, laid_at=today_dt)
        EggFactory.create_batch(2, chicken=c2, laid_at=today_dt)

        url = reverse("metrics")
        response = client.get(
            url,
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk), str(c2.pk)],
                "show_mean": "1",
                "start": start.isoformat(),
                "end": today.isoformat(),
                "w": "1",
            },
        )
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        mean_data = next(d["data"] for d in datasets if d["label"] == "Mean")
        assert mean_data[-1] == 2.0
