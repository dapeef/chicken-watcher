import json
from datetime import UTC, datetime, timedelta

import pytest
from django.db.models import Q
from django.urls import reverse

from test.web_app.factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
)
from web_app.views.metrics import _build_egg_prod_datasets


@pytest.mark.django_db
class TestMetricsViewQualityEggs:
    """
    Tests for:
    - include_non_saleable param parsing
    - per-quality-tier context keys (saleable/edible/messy _prod_datasets_json)
      and their contents
    - include_non_saleable effect on egg_prod, tod_egg, and nesting box pie charts
    """

    def _base_params(self, start, end):
        return {
            "chickens_sent": "1",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "w": "1",
        }

    def test_fresh_load_include_non_saleable_defaults_false(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["include_non_saleable"] is False

    def test_form_submission_include_non_saleable_off_by_default(self, client):
        response = client.get(reverse("metrics"), {"chickens_sent": "1"})
        assert response.context["include_non_saleable"] is False

    def test_include_non_saleable_explicit_on(self, client):
        response = client.get(
            reverse("metrics"), {"chickens_sent": "1", "include_non_saleable": "1"}
        )
        assert response.context["include_non_saleable"] is True

    def test_quality_prod_context_keys_present(self, client):
        response = client.get(reverse("metrics"))
        assert "saleable_prod_datasets_json" in response.context
        assert "edible_prod_datasets_json" in response.context
        assert "messy_prod_datasets_json" in response.context

    def test_quality_prod_context_keys_are_valid_json(self, client):
        response = client.get(reverse("metrics"))
        for key in (
            "saleable_prod_datasets_json",
            "edible_prod_datasets_json",
            "messy_prod_datasets_json",
        ):
            datasets = json.loads(response.context[key])
            assert isinstance(datasets, list)

    def test_messy_chart_counts_only_messy_eggs(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt, quality="messy")
        EggFactory.create_batch(5, chicken=hen, laid_at=today_dt, quality="saleable")
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt, quality="edible")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert hen_data[-1] == 3

    def test_edible_chart_counts_only_edible_eggs(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(4, chicken=hen, laid_at=today_dt, quality="edible")
        EggFactory.create_batch(6, chicken=hen, laid_at=today_dt, quality="saleable")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["edible_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert hen_data[-1] == 4

    def test_saleable_chart_counts_only_saleable_eggs(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(7, chicken=hen, laid_at=today_dt, quality="saleable")
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt, quality="messy")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["saleable_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert hen_data[-1] == 7

    def test_messy_chart_zero_when_no_messy_eggs(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(4, chicken=hen, laid_at=today_dt, quality="saleable")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert all(v == 0 or v is None for v in hen_data)

    def test_quality_chart_respects_date_range(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=10))
        before_range = datetime.combine(
            start - timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
        EggFactory.create_batch(3, chicken=hen, laid_at=before_range, quality="messy")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert all(v == 0 or v is None for v in hen_data)

    def test_quality_chart_respects_chicken_selection(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=c2, laid_at=today_dt, quality="messy")

        params = {**self._base_params(start, today), "chickens": str(c1.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert c1.name in labels
        assert c2.name not in labels

    def test_quality_chart_multiple_hens(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=c1, laid_at=today_dt, quality="messy")
        EggFactory.create_batch(4, chicken=c2, laid_at=today_dt, quality="messy")

        params = {
            **self._base_params(start, today),
            "chickens": [str(c1.pk), str(c2.pk)],
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        c1_data = next(d["data"] for d in datasets if d["label"] == c1.name)
        c2_data = next(d["data"] for d in datasets if d["label"] == c2.name)
        assert c1_data[-1] == 2
        assert c2_data[-1] == 4

    def test_include_non_saleable_adds_non_saleable_to_egg_prod(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt, quality="saleable")
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt, quality="messy")
        EggFactory.create_batch(1, chicken=hen, laid_at=today_dt, quality="edible")

        base = {**self._base_params(start, today), "chickens": str(hen.pk)}
        r_without = client.get(reverse("metrics"), base)
        r_with = client.get(reverse("metrics"), {**base, "include_non_saleable": "1"})

        def last_value(response):
            datasets = json.loads(response.context["egg_prod_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == hen.name)[-1]

        assert last_value(r_without) == 3
        assert last_value(r_with) == 6

    def test_include_non_saleable_off_does_not_affect_saleable_count(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(4, chicken=hen, laid_at=today_dt, quality="saleable")

        base = {**self._base_params(start, today), "chickens": str(hen.pk)}
        r_off = client.get(reverse("metrics"), base)
        r_on = client.get(reverse("metrics"), {**base, "include_non_saleable": "1"})

        def last_value(response):
            datasets = json.loads(response.context["egg_prod_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == hen.name)[-1]

        assert last_value(r_off) == 4
        assert last_value(r_on) == 4

    def test_include_non_saleable_changes_tod_egg_kde(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        midnight_dt = datetime.combine(
            today, datetime.min.time(), tzinfo=UTC
        )
        noon_dt = midnight_dt.replace(hour=12)
        EggFactory.create_batch(
            10, chicken=hen, laid_at=midnight_dt, quality="saleable"
        )
        EggFactory.create_batch(10, chicken=hen, laid_at=noon_dt, quality="messy")

        base = {**self._base_params(start, today), "chickens": str(hen.pk)}
        r_without = client.get(reverse("metrics"), base)
        r_with = client.get(reverse("metrics"), {**base, "include_non_saleable": "1"})

        def hen_kde(response):
            datasets = json.loads(response.context["tod_egg_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == hen.name)

        kde_without = hen_kde(r_without)
        kde_with = hen_kde(r_with)
        assert kde_with != kde_without
        peak_without = kde_without.index(max(kde_without))
        NOON_BUCKET = 72
        assert peak_without != NOON_BUCKET

    def test_include_non_saleable_adds_non_saleable_to_box_pie(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(
            3, chicken=hen, nesting_box=box, laid_at=today_dt, quality="saleable"
        )
        EggFactory.create_batch(
            2, chicken=hen, nesting_box=box, laid_at=today_dt, quality="messy"
        )

        base = {**self._base_params(start, today), "chickens": str(hen.pk)}
        r_off = client.get(reverse("metrics"), base)
        r_on = client.get(reverse("metrics"), {**base, "include_non_saleable": "1"})

        def box_count(response):
            data = json.loads(response.context["nesting_box_eggs_json"])
            return dict(zip(data["labels"], data["datasets"][0]["data"])).get("Left", 0)

        assert box_count(r_off) == 3
        assert box_count(r_on) == 5

    @pytest.mark.django_db
    def test_build_helper_quality_filter_isolates_messy(self):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        data_start = start - timedelta(days=1)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt, quality="messy")
        EggFactory.create_batch(5, chicken=hen, laid_at=today_dt, quality="saleable")

        days = (today - start).days + 1
        data_date_labels = [data_start + timedelta(days=i) for i in range(days + 1)]

        datasets = _build_egg_prod_datasets(
            chosen=[hen],
            data_date_labels=data_date_labels,
            window=1,
            base_egg_filter=Q(quality="messy"),
            show_sum=False,
            show_mean=False,
            include_unknown=False,
            data_start=data_start,
            end=today,
        )
        assert len(datasets) == 1
        assert datasets[0]["label"] == hen.name
        values = [v for v in datasets[0]["data"] if v is not None]
        assert values[-1] == 2

    @pytest.mark.django_db
    def test_build_helper_quality_filter_isolates_edible(self):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        data_start = start - timedelta(days=1)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt, quality="edible")
        EggFactory.create_batch(4, chicken=hen, laid_at=today_dt, quality="saleable")

        days = (today - start).days + 1
        data_date_labels = [data_start + timedelta(days=i) for i in range(days + 1)]

        datasets = _build_egg_prod_datasets(
            chosen=[hen],
            data_date_labels=data_date_labels,
            window=1,
            base_egg_filter=Q(quality="edible"),
            show_sum=False,
            show_mean=False,
            include_unknown=False,
            data_start=data_start,
            end=today,
        )
        values = [v for v in datasets[0]["data"] if v is not None]
        assert values[-1] == 3

    @pytest.mark.django_db
    def test_build_helper_empty_filter_counts_all(self):
        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        data_start = start - timedelta(days=1)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt, quality="messy")
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt, quality="saleable")

        days = (today - start).days + 1
        data_date_labels = [data_start + timedelta(days=i) for i in range(days + 1)]

        datasets = _build_egg_prod_datasets(
            chosen=[hen],
            data_date_labels=data_date_labels,
            window=1,
            base_egg_filter=Q(),
            show_sum=False,
            show_mean=False,
            include_unknown=False,
            data_start=data_start,
            end=today,
        )
        values = [v for v in datasets[0]["data"] if v is not None]
        assert values[-1] == 5
