import json
from datetime import UTC, datetime, timedelta

import pytest
from django.urls import reverse

from test.web_app.factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
)


@pytest.mark.django_db
class TestMetricsViewUnknownChicken:
    """
    Eggs with chicken=NULL are 'unattributed'. When include_unknown is on
    (the default on fresh page loads) they should appear as an "Unknown" series
    in the egg production and egg time-of-day charts, and be included in the
    nesting-box-by-eggs pie chart.  When the toggle is off they should be
    completely absent.
    """

    def _base_params(self, start, end):
        return {
            "chickens_sent": "1",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "w": "1",
        }

    def test_fresh_load_include_unknown_defaults_true(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["include_unknown"] is True

    def test_form_submission_include_unknown_off_by_default(self, client):
        response = client.get(reverse("metrics"), {"chickens_sent": "1"})
        assert response.context["include_unknown"] is False

    def test_include_unknown_explicit_on(self, client):
        response = client.get(reverse("metrics"), {"chickens_sent": "1", "include_unknown": "1"})
        assert response.context["include_unknown"] is True

    def test_unknown_series_present_in_egg_prod_when_enabled(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        assert "Unknown" in [d["label"] for d in datasets]

    def test_unknown_series_absent_from_egg_prod_when_disabled(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        response = client.get(reverse("metrics"), self._base_params(start, today))
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        assert "Unknown" not in [d["label"] for d in datasets]

    def test_unknown_egg_prod_series_counts_correctly(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(4, chicken=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        unknown_data = next(d["data"] for d in datasets if d["label"] == "Unknown")
        assert unknown_data[-1] == 4

    def test_unknown_eggs_not_counted_for_named_chickens(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt)
        EggFactory.create_batch(5, chicken=None, laid_at=today_dt)

        params = {
            **self._base_params(start, today),
            "chickens": str(hen.pk),
            "include_unknown": "1",
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert hen_data[-1] == 2

    def test_unknown_eggs_outside_date_range_excluded(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        before_range = datetime.combine(start - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=None, laid_at=before_range)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        unknown_data = next(d["data"] for d in datasets if d["label"] == "Unknown")
        assert all(v == 0 for v in unknown_data)

    def test_no_unknown_series_when_no_unknown_eggs_exist(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory(chicken=hen, laid_at=today_dt)

        params = {
            **self._base_params(start, today),
            "chickens": str(hen.pk),
            "include_unknown": "1",
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        unknown_data = next(d["data"] for d in datasets if d["label"] == "Unknown")
        assert all(v == 0 for v in unknown_data)

    def test_unknown_series_present_in_tod_egg_when_enabled(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["tod_egg_datasets_json"])
        assert "Unknown" in [d["label"] for d in datasets]

    def test_unknown_series_absent_from_tod_egg_when_disabled(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=None, laid_at=today_dt)

        response = client.get(reverse("metrics"), self._base_params(start, today))
        datasets = json.loads(response.context["tod_egg_datasets_json"])
        assert "Unknown" not in [d["label"] for d in datasets]

    def test_unknown_tod_kde_is_nonzero_when_eggs_exist(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["tod_egg_datasets_json"])
        unknown_kde = next(d["data"] for d in datasets if d["label"] == "Unknown")
        assert any(v > 0 for v in unknown_kde)

    def test_unknown_tod_kde_does_not_affect_named_hen_series(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt)

        base_params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        r_without = client.get(reverse("metrics"), base_params)
        r_with = client.get(reverse("metrics"), {**base_params, "include_unknown": "1"})
        EggFactory.create_batch(5, chicken=None, laid_at=today_dt)
        r_with_eggs = client.get(reverse("metrics"), {**base_params, "include_unknown": "1"})

        def hen_kde(response):
            datasets = json.loads(response.context["tod_egg_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == hen.name)

        assert hen_kde(r_without) == hen_kde(r_with)
        assert hen_kde(r_without) == hen_kde(r_with_eggs)

    def test_unknown_eggs_included_in_tod_egg_sum(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        base_params = {
            **self._base_params(start, today),
            "chickens": str(hen.pk),
            "show_sum": "1",
        }
        r_off = client.get(reverse("metrics"), base_params)
        r_on = client.get(reverse("metrics"), {**base_params, "include_unknown": "1"})

        def sum_kde(response):
            datasets = json.loads(response.context["tod_egg_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == "Sum")

        assert sum_kde(r_on) != sum_kde(r_off)
        assert all(a >= b for a, b in zip(sum_kde(r_on), sum_kde(r_off)))

    def test_unknown_eggs_excluded_from_tod_egg_sum_when_disabled(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        params = {
            **self._base_params(start, today),
            "chickens": str(hen.pk),
            "show_sum": "1",
        }
        r_off = client.get(reverse("metrics"), params)
        r_hen_only = client.get(reverse("metrics"), {**params, "chickens": str(hen.pk)})

        def sum_kde(response):
            datasets = json.loads(response.context["tod_egg_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == "Sum")

        assert sum_kde(r_off) == sum_kde(r_hen_only)

    def test_tod_egg_mean_denominator_is_named_chickens_only(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(5, chicken=hen, laid_at=today_dt)
        EggFactory.create_batch(5, chicken=None, laid_at=today_dt)

        params = {
            **self._base_params(start, today),
            "chickens": str(hen.pk),
            "show_sum": "1",
            "show_mean": "1",
            "include_unknown": "1",
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["tod_egg_datasets_json"])
        sum_data = next(d["data"] for d in datasets if d["label"] == "Sum")
        mean_data = next(d["data"] for d in datasets if d["label"] == "Mean")
        assert all(abs(m - s) < 1e-5 for m, s in zip(mean_data, sum_data))

    def test_unknown_chicken_eggs_included_in_box_pie_when_enabled(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=None, nesting_box=box, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        box_eggs = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
        assert box_eggs.get("Left", 0) == 3

    def test_unknown_chicken_eggs_excluded_from_box_pie_when_disabled(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=None, nesting_box=box, laid_at=today_dt)

        response = client.get(reverse("metrics"), self._base_params(start, today))
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        assert eggs_data["labels"] == []

    def test_unknown_chicken_and_unknown_box_shows_unknown_label(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=None, nesting_box=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        box_eggs = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
        assert box_eggs.get("Unknown", 0) == 2

    def test_known_chicken_eggs_unaffected_by_unknown_toggle(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(4, chicken=hen, nesting_box=box, laid_at=today_dt)
        EggFactory.create_batch(2, chicken=None, nesting_box=box, laid_at=today_dt)

        base_params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        r_off = client.get(reverse("metrics"), base_params)
        r_on = client.get(reverse("metrics"), {**base_params, "include_unknown": "1"})

        def box_count(response):
            eggs_data = json.loads(response.context["nesting_box_eggs_json"])
            mapping = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
            return mapping.get("Left", 0)

        assert box_count(r_off) == 4
        assert box_count(r_on) == 6
