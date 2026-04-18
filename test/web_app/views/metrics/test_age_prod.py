import json
from datetime import UTC, datetime, timedelta

import pytest
from django.urls import reverse

from test.web_app.factories import ChickenFactory, EggFactory


@pytest.mark.django_db
class TestMetricsViewAgeProd:
    """
    Tests for the egg-production-vs-age chart:
    - context keys present
    - x-axis labels are age-in-days integers
    - each hen's series is keyed by age, not calendar date
    - chicken selection is respected
    - rolling window is applied correctly
    - include_non_saleable filter is respected
    """

    def _params(self, start, end, chickens, window=1):
        p = {
            "chickens_sent": "1",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "age_w": str(window),
        }
        if chickens:
            p["chickens"] = [str(c.pk) for c in chickens]
        return p

    def test_age_prod_labels_json_in_context(self, client):
        response = client.get(reverse("metrics"))
        assert "age_prod_labels_json" in response.context

    def test_age_prod_datasets_json_in_context(self, client):
        response = client.get(reverse("metrics"))
        assert "age_prod_datasets_json" in response.context

    def test_age_prod_labels_are_integers(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=10))
        response = client.get(reverse("metrics"), self._params(start, today, [hen]))
        labels = json.loads(response.context["age_prod_labels_json"])
        assert all(isinstance(v, int) for v in labels)
        assert labels == list(range(len(labels)))

    def test_egg_counted_at_correct_age(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=200)
        hen = ChickenFactory(date_of_birth=dob)
        egg_date = dob + timedelta(days=100)
        start = egg_date - timedelta(days=6)
        end = egg_date + timedelta(days=6)
        egg_dt = datetime.combine(egg_date, datetime.min.time(), tzinfo=UTC)
        EggFactory(chicken=hen, laid_at=egg_dt)

        response = client.get(reverse("metrics"), self._params(start, end, [hen]))
        datasets = json.loads(response.context["age_prod_datasets_json"])
        assert len(datasets) == 1
        data = datasets[0]["data"]
        labels = json.loads(response.context["age_prod_labels_json"])
        age_idx = labels.index(100)
        assert data[age_idx] == 1

    def test_two_hens_same_calendar_date_different_age(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        egg_date = today - timedelta(days=5)
        dob_old = egg_date - timedelta(days=200)
        dob_young = egg_date - timedelta(days=50)
        hen_old = ChickenFactory(date_of_birth=dob_old)
        hen_young = ChickenFactory(date_of_birth=dob_young)

        start = egg_date - timedelta(days=1)
        end = egg_date + timedelta(days=1)
        egg_dt = datetime.combine(egg_date, datetime.min.time(), tzinfo=UTC)
        EggFactory(chicken=hen_old, laid_at=egg_dt)
        EggFactory(chicken=hen_young, laid_at=egg_dt)

        response = client.get(
            reverse("metrics"), self._params(start, end, [hen_old, hen_young])
        )
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = json.loads(response.context["age_prod_labels_json"])

        old_data = next(d["data"] for d in datasets if d["label"] == hen_old.name)
        young_data = next(d["data"] for d in datasets if d["label"] == hen_young.name)

        assert old_data[labels.index(200)] == 1
        assert young_data[labels.index(50)] == 1
        assert old_data[labels.index(50)] == 0
        assert young_data[labels.index(200)] is None

    def test_eggs_before_start_still_appear_in_age_chart(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=200)
        hen = ChickenFactory(date_of_birth=dob)
        start = today - timedelta(days=6)
        age_100_date = dob + timedelta(days=100)
        egg_dt = datetime.combine(
            age_100_date, datetime.min.time(), tzinfo=UTC
        )
        EggFactory(chicken=hen, laid_at=egg_dt)

        response = client.get(reverse("metrics"), self._params(start, today, [hen]))
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = json.loads(response.context["age_prod_labels_json"])
        data = datasets[0]["data"]
        assert data[labels.index(100)] == 1

    def test_unselected_hen_absent_from_datasets(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=50))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=50))

        response = client.get(reverse("metrics"), self._params(start, today, [c1]))
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels_in_data = {d["label"] for d in datasets}
        assert c1.name in labels_in_data
        assert c2.name not in labels_in_data

    def test_no_chickens_selected_gives_empty_datasets(self, client):
        ChickenFactory()
        response = client.get(reverse("metrics"), {"chickens_sent": "1"})
        datasets = json.loads(response.context["age_prod_datasets_json"])
        assert datasets == []

    def test_rolling_window_smooths_age_prod(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=200)
        hen = ChickenFactory(date_of_birth=dob)
        start = today - timedelta(days=6)

        for offset in range(3):
            egg_dt = datetime.combine(
                today - timedelta(days=2 - offset),
                datetime.min.time(),
                tzinfo=UTC,
            )
            EggFactory(chicken=hen, laid_at=egg_dt)

        params_w1 = self._params(start, today, [hen], window=1)
        params_w3 = self._params(start, today, [hen], window=3)

        r1 = client.get(reverse("metrics"), params_w1)
        r3 = client.get(reverse("metrics"), params_w3)

        data_w1 = json.loads(r1.context["age_prod_datasets_json"])[0]["data"]
        data_w3 = json.loads(r3.context["age_prod_datasets_json"])[0]["data"]

        non_none_w1 = [v for v in data_w1 if v is not None]
        assert non_none_w1[-3:] == [1.0, 1.0, 1.0]

        non_none_w3 = [v for v in data_w3 if v is not None]
        assert non_none_w3[-1] == 1.0

    def test_non_saleable_excluded_from_age_prod_by_default(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=200)
        hen = ChickenFactory(date_of_birth=dob)
        start = today - timedelta(days=6)
        egg_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory(chicken=hen, laid_at=egg_dt, quality="saleable")
        EggFactory(chicken=hen, laid_at=egg_dt, quality="messy")

        base = self._params(start, today, [hen])
        r_off = client.get(reverse("metrics"), base)
        r_on = client.get(reverse("metrics"), {**base, "include_non_saleable": "1"})

        def last_non_none(response):
            data = json.loads(response.context["age_prod_datasets_json"])[0]["data"]
            return next(v for v in reversed(data) if v is not None)

        assert last_non_none(r_off) == 1
        assert last_non_none(r_on) == 2

    def test_show_mean_adds_mean_to_age_prod(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=100)
        hen = ChickenFactory(date_of_birth=dob)
        egg_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory(chicken=hen, laid_at=egg_dt)

        params = {
            **self._params(today - timedelta(days=6), today, [hen]),
            "show_mean": "1",
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["age_prod_datasets_json"])
        assert "Mean" in {d["label"] for d in datasets}

    def test_show_sum_adds_sum_to_age_prod(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=100)
        hen = ChickenFactory(date_of_birth=dob)
        egg_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory(chicken=hen, laid_at=egg_dt)

        params = {
            **self._params(today - timedelta(days=6), today, [hen]),
            "show_sum": "1",
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["age_prod_datasets_json"])
        assert "Sum" in {d["label"] for d in datasets}

    def test_mean_value_is_average_across_hens(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=100)
        c1 = ChickenFactory(date_of_birth=dob)
        c2 = ChickenFactory(date_of_birth=dob)
        egg_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=c1, laid_at=egg_dt)
        EggFactory.create_batch(4, chicken=c2, laid_at=egg_dt)

        params = {
            **self._params(today - timedelta(days=6), today, [c1, c2]),
            "show_mean": "1",
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = json.loads(response.context["age_prod_labels_json"])
        mean_data = next(d["data"] for d in datasets if d["label"] == "Mean")
        assert mean_data[labels.index(100)] == 3.0

    def test_no_sum_or_mean_without_flags(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        hen = ChickenFactory(date_of_birth=today - timedelta(days=100))
        params = self._params(today - timedelta(days=6), today, [hen])
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert "Sum" not in labels
        assert "Mean" not in labels
