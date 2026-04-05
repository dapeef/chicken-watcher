import json
import pytest
from datetime import date, timedelta, datetime, timezone as dt_timezone
from django.urls import reverse

from web_app.views.metrics import (
    _gaussian_smooth_circular,
    DEFAULT_SPAN,
    DEFAULT_WINDOW,
    DEFAULT_NEST_SIGMA,
)
from web_app.views.chickens import BUCKETS_PER_DAY, BUCKET_MINUTES
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxPresencePeriodFactory,
    NestingBoxFactory,
)


# ── _gaussian_smooth_circular ─────────────────────────────────────────────────


class TestGaussianSmoothCircular:
    def test_sigma_zero_returns_floats_equal_to_input(self):
        counts = list(range(BUCKETS_PER_DAY))
        result = _gaussian_smooth_circular(counts, 0)
        assert result == [float(v) for v in counts]

    def test_output_length_is_buckets_per_day(self):
        counts = [1] * BUCKETS_PER_DAY
        assert len(_gaussian_smooth_circular(counts, 20)) == BUCKETS_PER_DAY

    def test_all_zeros_stays_all_zeros(self):
        counts = [0] * BUCKETS_PER_DAY
        result = _gaussian_smooth_circular(counts, 20)
        assert all(v == 0.0 for v in result)

    def test_single_spike_peak_at_spike_location(self):
        counts = [0] * BUCKETS_PER_DAY
        spike_bucket = 60  # 10:00
        counts[spike_bucket] = 10
        result = _gaussian_smooth_circular(counts, 20)
        assert result.index(max(result)) == spike_bucket

    def test_single_spike_symmetric_falloff(self):
        counts = [0] * BUCKETS_PER_DAY
        spike_bucket = 60
        counts[spike_bucket] = 10
        result = _gaussian_smooth_circular(counts, 20)
        # Buckets equidistant from the spike should be equal
        assert abs(result[spike_bucket - 1] - result[spike_bucket + 1]) < 1e-6

    def test_wraps_at_midnight(self):
        # Spike at bucket 0 (00:00) should spread to the last bucket as well
        counts = [0] * BUCKETS_PER_DAY
        counts[0] = 10
        result = _gaussian_smooth_circular(counts, 30)
        # Last bucket should be non-zero due to circular wrap
        assert result[-1] > 0
        # And by symmetry result[-1] ≈ result[1]
        assert abs(result[-1] - result[1]) < 1e-4

    def test_smoothing_reduces_peak_value(self):
        counts = [0] * BUCKETS_PER_DAY
        counts[60] = 10
        result = _gaussian_smooth_circular(counts, 20)
        assert max(result) < 10

    def test_smoothing_preserves_total_mass(self):
        # The weighted average is normalised, so sum of smoothed values
        # equals sum of input values (all ones → all ones)
        counts = [1] * BUCKETS_PER_DAY
        result = _gaussian_smooth_circular(counts, 20)
        assert all(abs(v - 1.0) < 1e-4 for v in result)


# ── MetricsView ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMetricsViewDefaults:
    def test_returns_200(self, client):
        response = client.get(reverse("metrics"))
        assert response.status_code == 200

    def test_all_expected_context_keys_present(self, client):
        response = client.get(reverse("metrics"))
        for key in (
            "all_chickens",
            "selected_ids",
            "chickens_sent",
            "show_sum",
            "show_mean",
            "start",
            "end",
            "window",
            "window_choices",
            "nest_sigma",
            "nest_sigma_choices",
            "egg_prod_labels_json",
            "egg_prod_datasets_json",
            "flock_count_dataset_json",
            "tod_labels_json",
            "tod_egg_datasets_json",
            "tod_nest_datasets_json",
            "today",
            "earliest_dob",
        ):
            assert key in response.context, f"Missing context key: {key}"

    def test_fresh_load_defaults_all_chickens_selected(self, client):
        c1 = ChickenFactory()
        c2 = ChickenFactory()
        response = client.get(reverse("metrics"))
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert c1.name in labels
        assert c2.name in labels

    def test_fresh_load_show_mean_defaults_true(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["show_mean"] is True

    def test_fresh_load_show_sum_defaults_false(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["show_sum"] is False

    def test_default_date_range_is_90_days(self, client):
        response = client.get(reverse("metrics"))
        start = date.fromisoformat(response.context["start"])
        end = date.fromisoformat(response.context["end"])
        assert (end - start).days == DEFAULT_SPAN - 1

    def test_default_rolling_window(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["window"] == DEFAULT_WINDOW

    def test_default_nest_sigma(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["nest_sigma"] == DEFAULT_NEST_SIGMA


@pytest.mark.django_db
class TestMetricsViewChickenSelection:
    def test_specific_chicken_ids_limits_datasets(self, client):
        c1 = ChickenFactory()
        c2 = ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1", "chickens": str(c1.pk)})
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert c1.name in labels
        assert c2.name not in labels

    def test_chickens_sent_with_no_ids_gives_empty_datasets(self, client):
        ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1"})
        assert response.context["chickens_sent"] is True
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        assert datasets == []

    def test_chickens_sent_empty_selection_no_flock_counts(self, client):
        ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1"})
        flock = json.loads(response.context["flock_count_dataset_json"])
        assert all(v == 0 for v in flock["data"])

    def test_invalid_chicken_id_ignored(self, client):
        c1 = ChickenFactory()
        url = reverse("metrics")
        response = client.get(
            url, {"chickens_sent": "1", "chickens": [str(c1.pk), "99999"]}
        )
        assert response.status_code == 200
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert c1.name in labels


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
        today = date.today()
        start = today - timedelta(days=6)

        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))

        # 2 eggs today for c1, 3 for c2 → sum should include 5
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
                "w": "1",  # window=1 so rolling avg == raw count
            },
        )
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        sum_data = next(d["data"] for d in datasets if d["label"] == "Sum")
        # Last value should be 5 (today's eggs)
        assert sum_data[-1] == 5

    def test_mean_values_equal_sum_divided_by_n(self, client):
        today = date.today()
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
        # 2 eggs each → mean = 2.0
        assert mean_data[-1] == 2.0


@pytest.mark.django_db
class TestMetricsViewParamValidation:
    def test_invalid_rolling_window_falls_back_to_default(self, client):
        response = client.get(reverse("metrics"), {"w": "99"})
        assert response.context["window"] == DEFAULT_WINDOW

    def test_non_numeric_rolling_window_falls_back_to_default(self, client):
        response = client.get(reverse("metrics"), {"w": "banana"})
        assert response.context["window"] == DEFAULT_WINDOW

    def test_invalid_nest_sigma_falls_back_to_default(self, client):
        response = client.get(reverse("metrics"), {"nest_sigma": "999"})
        assert response.context["nest_sigma"] == DEFAULT_NEST_SIGMA

    def test_non_numeric_nest_sigma_falls_back_to_default(self, client):
        response = client.get(reverse("metrics"), {"nest_sigma": "smooth"})
        assert response.context["nest_sigma"] == DEFAULT_NEST_SIGMA

    def test_invalid_date_strings_fall_back_to_default_range(self, client):
        response = client.get(
            reverse("metrics"), {"start": "not-a-date", "end": "also-not"}
        )
        end = date.fromisoformat(response.context["end"])
        start = date.fromisoformat(response.context["start"])
        assert (end - start).days == DEFAULT_SPAN - 1

    def test_start_equal_to_end_falls_back_to_default_range(self, client):
        today = date.today().isoformat()
        response = client.get(reverse("metrics"), {"start": today, "end": today})
        start = date.fromisoformat(response.context["start"])
        end = date.fromisoformat(response.context["end"])
        assert (end - start).days == DEFAULT_SPAN - 1

    def test_start_after_end_falls_back_to_default_range(self, client):
        today = date.today()
        response = client.get(
            reverse("metrics"),
            {
                "start": today.isoformat(),
                "end": (today - timedelta(days=10)).isoformat(),
            },
        )
        start = date.fromisoformat(response.context["start"])
        end = date.fromisoformat(response.context["end"])
        assert (end - start).days == DEFAULT_SPAN - 1


@pytest.mark.django_db
class TestMetricsViewFlockCount:
    def test_flock_count_reflects_alive_chickens_only(self, client):
        today = date.today()
        start = today - timedelta(days=4)

        # c1 alive throughout; c2 dies 2 days ago
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

        # First day: both alive → 2
        assert data[0] == 2
        # Last day (today): only c1 alive → 1
        assert data[-1] == 1

    def test_flock_count_zero_before_any_dob(self, client):
        today = date.today()
        # Chicken born today
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

        # First two days: chicken not yet born → 0
        assert data[0] == 0
        assert data[1] == 0
        # Last day: chicken alive → 1
        assert data[-1] == 1
