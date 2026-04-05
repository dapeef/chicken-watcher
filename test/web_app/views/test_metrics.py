import json
import pytest
from datetime import date, timedelta, datetime, timezone as dt_timezone
from django.urls import reverse

from web_app.views.metrics import (
    _gaussian_smooth_circular,
    DEFAULT_SPAN,
    DEFAULT_WINDOW,
    DEFAULT_NEST_SIGMA,
    DEFAULT_KDE_BANDWIDTH,
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


@pytest.mark.django_db
class TestMetricsViewNestingBoxPreference:
    def test_context_keys_present(self, client):
        response = client.get(reverse("metrics"))
        assert "nesting_box_visits_json" in response.context
        assert "nesting_box_time_json" in response.context

    def test_visits_counted_per_box(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_a = NestingBoxFactory(name="left")
        box_b = NestingBoxFactory(name="right")

        # 3 visits to left, 1 visit to right
        for _ in range(3):
            NestingBoxPresencePeriodFactory(
                chicken=hen,
                nesting_box=box_a,
                started_at=datetime.combine(
                    today, datetime.min.time(), tzinfo=dt_timezone.utc
                ),
                ended_at=datetime.combine(
                    today, datetime.min.time(), tzinfo=dt_timezone.utc
                )
                + timedelta(minutes=10),
            )
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_b,
            started_at=datetime.combine(
                today, datetime.min.time(), tzinfo=dt_timezone.utc
            ),
            ended_at=datetime.combine(
                today, datetime.min.time(), tzinfo=dt_timezone.utc
            )
            + timedelta(minutes=5),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        box_visits = dict(
            zip(visits_data["labels"], visits_data["datasets"][0]["data"])
        )
        assert box_visits["left"] == 3
        assert box_visits["right"] == 1

    def test_time_summed_per_box(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_a = NestingBoxFactory(name="left")
        box_b = NestingBoxFactory(name="right")

        base = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        # 2 × 30-minute visits to left = 3600 s; 1 × 10-minute visit to right = 600 s
        for _ in range(2):
            NestingBoxPresencePeriodFactory(
                chicken=hen,
                nesting_box=box_a,
                started_at=base,
                ended_at=base + timedelta(minutes=30),
            )
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box_b,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        time_data = json.loads(response.context["nesting_box_time_json"])
        box_secs = dict(zip(time_data["labels"], time_data["datasets"][0]["data"]))
        assert box_secs["left"] == 3600
        assert box_secs["right"] == 600

    def test_aggregates_across_multiple_chickens(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        base = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)

        # 1 visit each from c1 and c2 → total 2 visits
        NestingBoxPresencePeriodFactory(
            chicken=c1,
            nesting_box=box,
            started_at=base,
            ended_at=base + timedelta(minutes=20),
        )
        NestingBoxPresencePeriodFactory(
            chicken=c2,
            nesting_box=box,
            started_at=base,
            ended_at=base + timedelta(minutes=40),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk), str(c2.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        box_visits = dict(
            zip(visits_data["labels"], visits_data["datasets"][0]["data"])
        )
        assert box_visits["left"] == 2

        time_data = json.loads(response.context["nesting_box_time_json"])
        box_secs = dict(zip(time_data["labels"], time_data["datasets"][0]["data"]))
        assert box_secs["left"] == (20 + 40) * 60

    def test_excludes_periods_outside_date_range(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=10))
        box = NestingBoxFactory(name="left")
        before_range = datetime.combine(
            start - timedelta(days=1), datetime.min.time(), tzinfo=dt_timezone.utc
        )
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box,
            started_at=before_range,
            ended_at=before_range + timedelta(minutes=30),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        assert visits_data["labels"] == []
        assert visits_data["datasets"][0]["data"] == []

    def test_excludes_unselected_chickens(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        base = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)

        # Only c2 has a visit; we select only c1
        NestingBoxPresencePeriodFactory(
            chicken=c2,
            nesting_box=box,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        assert visits_data["labels"] == []

    def test_empty_when_no_chickens_selected(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        base = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        NestingBoxPresencePeriodFactory(
            chicken=hen,
            nesting_box=box,
            started_at=base,
            ended_at=base + timedelta(minutes=10),
        )

        response = client.get(reverse("metrics"), {"chickens_sent": "1"})
        visits_data = json.loads(response.context["nesting_box_visits_json"])
        assert visits_data["labels"] == []
        assert visits_data["datasets"][0]["data"] == []

    def test_eggs_context_key_present(self, client):
        response = client.get(reverse("metrics"))
        assert "nesting_box_eggs_json" in response.context

    def test_eggs_counted_per_box(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box_a = NestingBoxFactory(name="left")
        box_b = NestingBoxFactory(name="right")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)

        EggFactory.create_batch(4, chicken=hen, nesting_box=box_a, laid_at=today_dt)
        EggFactory.create_batch(1, chicken=hen, nesting_box=box_b, laid_at=today_dt)

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        box_eggs = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
        assert box_eggs["left"] == 4
        assert box_eggs["right"] == 1

    def test_eggs_aggregated_across_chickens(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)

        EggFactory.create_batch(2, chicken=c1, nesting_box=box, laid_at=today_dt)
        EggFactory.create_batch(3, chicken=c2, nesting_box=box, laid_at=today_dt)

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk), str(c2.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        box_eggs = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
        assert box_eggs["left"] == 5

    def test_eggs_excluded_outside_date_range(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=10))
        box = NestingBoxFactory(name="left")
        before_range = datetime.combine(
            start - timedelta(days=1), datetime.min.time(), tzinfo=dt_timezone.utc
        )
        EggFactory(chicken=hen, nesting_box=box, laid_at=before_range)

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(hen.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        assert eggs_data["labels"] == []

    def test_eggs_excluded_for_unselected_chickens(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory(chicken=c2, nesting_box=box, laid_at=today_dt)

        response = client.get(
            reverse("metrics"),
            {
                "chickens_sent": "1",
                "chickens": [str(c1.pk)],
                "start": start.isoformat(),
                "end": today.isoformat(),
            },
        )
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        assert eggs_data["labels"] == []  # c2's egg excluded


@pytest.mark.django_db
class TestMetricsViewKdeBandwidth:
    def test_default_bandwidth_in_context(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["kde_bandwidth"] == DEFAULT_KDE_BANDWIDTH

    def test_explicit_bandwidth_respected(self, client):
        response = client.get(reverse("metrics"), {"kde_bw": "10"})
        assert response.context["kde_bandwidth"] == 10

    def test_invalid_bandwidth_falls_back_to_default(self, client):
        response = client.get(reverse("metrics"), {"kde_bw": "99"})
        assert response.context["kde_bandwidth"] == DEFAULT_KDE_BANDWIDTH

    def test_non_numeric_bandwidth_falls_back_to_default(self, client):
        response = client.get(reverse("metrics"), {"kde_bw": "smooth"})
        assert response.context["kde_bandwidth"] == DEFAULT_KDE_BANDWIDTH

    def test_bandwidth_choices_in_context(self, client):
        response = client.get(reverse("metrics"))
        assert "kde_bandwidth_choices" in response.context

    def test_wider_bandwidth_produces_broader_kde(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(5, chicken=hen, laid_at=today_dt)

        url = reverse("metrics")
        params = {
            "chickens_sent": "1",
            "chickens": [str(hen.pk)],
            "start": start.isoformat(),
            "end": today.isoformat(),
        }

        r_narrow = client.get(url, {**params, "kde_bw": "5"})
        r_wide = client.get(url, {**params, "kde_bw": "60"})

        datasets_narrow = json.loads(r_narrow.context["tod_egg_datasets_json"])
        datasets_wide = json.loads(r_wide.context["tod_egg_datasets_json"])

        assert len(datasets_narrow) == 1
        assert len(datasets_wide) == 1

        # Narrow bandwidth → taller, sharper peak
        peak_narrow = max(datasets_narrow[0]["data"])
        peak_wide = max(datasets_wide[0]["data"])
        assert peak_narrow > peak_wide
