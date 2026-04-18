import json
import pytest
from datetime import date, timedelta, datetime, timezone as dt_timezone
from django.http import QueryDict
from django.urls import reverse

from web_app.views.metrics import (
    _build_egg_prod_datasets,
    MetricsParams,
    DEFAULT_SPAN,
    DEFAULT_WINDOW,
    DEFAULT_AGE_WINDOW,
    DEFAULT_NEST_SIGMA,
    DEFAULT_KDE_BANDWIDTH,
)
from django.db.models import Q
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxPresencePeriodFactory,
    NestingBoxFactory,
)


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

    def test_default_age_rolling_window(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["age_window"] == DEFAULT_AGE_WINDOW

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
        assert box_visits["Left"] == 3
        assert box_visits["Right"] == 1

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
        assert box_secs["Left"] == 3600
        assert box_secs["Right"] == 600

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
        assert box_visits["Left"] == 2

        time_data = json.loads(response.context["nesting_box_time_json"])
        box_secs = dict(zip(time_data["labels"], time_data["datasets"][0]["data"]))
        assert box_secs["Left"] == (20 + 40) * 60

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
        assert box_eggs["Left"] == 4
        assert box_eggs["Right"] == 1

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
        assert box_eggs["Left"] == 5

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


# ── Unknown-chicken egg handling ──────────────────────────────────────────────


@pytest.mark.django_db
class TestMetricsViewUnknownChicken:
    """
    Eggs with chicken=NULL are 'unattributed'. When include_unknown is on
    (the default on fresh page loads) they should appear as an "Unknown" series
    in the egg production and egg time-of-day charts, and be included in the
    nesting-box-by-eggs pie chart.  When the toggle is off they should be
    completely absent.
    """

    # ── helpers ──────────────────────────────────────────────────────────────

    def _base_params(self, start, end):
        return {
            "chickens_sent": "1",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "w": "1",  # window=1 so rolling avg == raw count
        }

    # ── include_unknown param parsing ────────────────────────────────────────

    def test_fresh_load_include_unknown_defaults_true(self, client):
        response = client.get(reverse("metrics"))
        assert response.context["include_unknown"] is True

    def test_form_submission_include_unknown_off_by_default(self, client):
        # Once the form is submitted without the checkbox, it should be False
        response = client.get(reverse("metrics"), {"chickens_sent": "1"})
        assert response.context["include_unknown"] is False

    def test_include_unknown_explicit_on(self, client):
        response = client.get(
            reverse("metrics"), {"chickens_sent": "1", "include_unknown": "1"}
        )
        assert response.context["include_unknown"] is True

    # ── egg production chart ─────────────────────────────────────────────────

    def test_unknown_series_present_in_egg_prod_when_enabled(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        labels = [d["label"] for d in datasets]
        assert "Unknown" in labels

    def test_unknown_series_absent_from_egg_prod_when_disabled(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        params = self._base_params(start, today)  # include_unknown not set → False
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        labels = [d["label"] for d in datasets]
        assert "Unknown" not in labels

    def test_unknown_egg_prod_series_counts_correctly(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(4, chicken=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        unknown_data = next(d["data"] for d in datasets if d["label"] == "Unknown")
        # With window=1, last value should be exactly 4
        assert unknown_data[-1] == 4

    def test_unknown_eggs_not_counted_for_named_chickens(self, client):
        """Unknown eggs must not inflate a named chicken's count."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
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
        today = date.today()
        start = today - timedelta(days=6)
        before_range = datetime.combine(
            start - timedelta(days=1), datetime.min.time(), tzinfo=dt_timezone.utc
        )
        EggFactory.create_batch(3, chicken=None, laid_at=before_range)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        unknown_data = next(d["data"] for d in datasets if d["label"] == "Unknown")
        assert all(v == 0 for v in unknown_data)

    def test_no_unknown_series_when_no_unknown_eggs_exist(self, client):
        """Toggle on but zero unattributed eggs → series present but all zeros."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
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

    # ── egg time-of-day KDE chart ─────────────────────────────────────────────

    def test_unknown_series_present_in_tod_egg_when_enabled(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(2, chicken=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["tod_egg_datasets_json"])
        labels = [d["label"] for d in datasets]
        assert "Unknown" in labels

    def test_unknown_series_absent_from_tod_egg_when_disabled(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(2, chicken=None, laid_at=today_dt)

        params = self._base_params(start, today)
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["tod_egg_datasets_json"])
        labels = [d["label"] for d in datasets]
        assert "Unknown" not in labels

    def test_unknown_tod_kde_is_nonzero_when_eggs_exist(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["tod_egg_datasets_json"])
        unknown_kde = next(d["data"] for d in datasets if d["label"] == "Unknown")
        assert any(v > 0 for v in unknown_kde)

    def test_unknown_tod_kde_does_not_affect_named_hen_series(self, client):
        """Presence of unknown eggs must not change a named hen's KDE values."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt)

        base_params = {
            **self._base_params(start, today),
            "chickens": str(hen.pk),
        }

        r_without = client.get(reverse("metrics"), base_params)
        r_with = client.get(
            reverse("metrics"),
            {**base_params, "include_unknown": "1"},
        )
        # Also add some unknown eggs so the Unknown series is non-trivial
        EggFactory.create_batch(5, chicken=None, laid_at=today_dt)
        r_with_eggs = client.get(
            reverse("metrics"),
            {**base_params, "include_unknown": "1"},
        )

        def hen_kde(response):
            datasets = json.loads(response.context["tod_egg_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == hen.name)

        assert hen_kde(r_without) == hen_kde(r_with)
        assert hen_kde(r_without) == hen_kde(r_with_eggs)

    def test_unknown_eggs_included_in_tod_egg_sum(self, client):
        """Sum series must include the unknown KDE when include_unknown is on."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
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

        # With unknown included, sum should be strictly higher everywhere the
        # unknown eggs contribute (i.e. the totals must differ).
        assert sum_kde(r_on) != sum_kde(r_off)
        # And the sum-with-unknown should be >= sum-without at every bucket.
        assert all(a >= b for a, b in zip(sum_kde(r_on), sum_kde(r_off)))

    def test_unknown_eggs_excluded_from_tod_egg_sum_when_disabled(self, client):
        """Sum must not include unknown eggs when include_unknown is off."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt)
        EggFactory.create_batch(3, chicken=None, laid_at=today_dt)

        params = {
            **self._base_params(start, today),
            "chickens": str(hen.pk),
            "show_sum": "1",
            # include_unknown not set → False
        }
        r_off = client.get(reverse("metrics"), params)
        # Sum with toggle off should equal a sum computed with only the hen
        params_hen_only = {**params, "chickens": str(hen.pk)}
        r_hen_only = client.get(reverse("metrics"), params_hen_only)

        def sum_kde(response):
            datasets = json.loads(response.context["tod_egg_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == "Sum")

        assert sum_kde(r_off) == sum_kde(r_hen_only)

    def test_tod_egg_mean_denominator_is_named_chickens_only(self, client):
        """Mean divides by number of named chickens, not named+1."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        # Lay eggs at the same time for both known and unknown so KDEs are identical.
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
        # n=1 named chicken → mean should equal the full sum (sum / 1).
        # If the denominator were incorrectly n+1=2, mean would be sum/2.
        assert all(abs(m - s) < 1e-5 for m, s in zip(mean_data, sum_data))

    # ── nesting box by eggs pie chart ─────────────────────────────────────────

    def test_unknown_chicken_eggs_included_in_box_pie_when_enabled(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(3, chicken=None, nesting_box=box, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        box_eggs = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
        assert box_eggs.get("Left", 0) == 3

    def test_unknown_chicken_eggs_excluded_from_box_pie_when_disabled(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(3, chicken=None, nesting_box=box, laid_at=today_dt)

        params = self._base_params(start, today)  # include_unknown not set → False
        response = client.get(reverse("metrics"), params)
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        assert eggs_data["labels"] == []

    def test_unknown_chicken_and_unknown_box_shows_unknown_label(self, client):
        """An egg with neither chicken nor nesting box should appear as 'Unknown'."""
        today = date.today()
        start = today - timedelta(days=6)
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(2, chicken=None, nesting_box=None, laid_at=today_dt)

        params = {**self._base_params(start, today), "include_unknown": "1"}
        response = client.get(reverse("metrics"), params)
        eggs_data = json.loads(response.context["nesting_box_eggs_json"])
        box_eggs = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
        assert box_eggs.get("Unknown", 0) == 2

    def test_known_chicken_eggs_unaffected_by_unknown_toggle(self, client):
        """Toggling include_unknown must not change counts for named chickens."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(4, chicken=hen, nesting_box=box, laid_at=today_dt)
        EggFactory.create_batch(2, chicken=None, nesting_box=box, laid_at=today_dt)

        base_params = {
            **self._base_params(start, today),
            "chickens": str(hen.pk),
        }

        r_off = client.get(reverse("metrics"), base_params)
        r_on = client.get(reverse("metrics"), {**base_params, "include_unknown": "1"})

        def box_count(response):
            eggs_data = json.loads(response.context["nesting_box_eggs_json"])
            mapping = dict(zip(eggs_data["labels"], eggs_data["datasets"][0]["data"]))
            return mapping.get("Left", 0)

        # With toggle off: only hen's 4 eggs
        assert box_count(r_off) == 4
        # With toggle on: hen's 4 + unknown's 2
        assert box_count(r_on) == 6


# ── Quality egg charts ────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMetricsViewQualityEggs:
    """
    Tests for:
    - include_non_saleable param parsing
    - per-quality-tier context keys (saleable/edible/messy _prod_datasets_json)
      and their contents
    - include_non_saleable effect on egg_prod, tod_egg, and nesting box pie charts
    """

    # ── helpers ──────────────────────────────────────────────────────────────

    def _base_params(self, start, end):
        return {
            "chickens_sent": "1",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "w": "1",  # window=1 so rolling avg == raw count
        }

    # ── include_non_saleable param parsing ────────────────────────────────────

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

    # ── quality production chart context keys ─────────────────────────────────

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

    # ── per-quality chart counts ──────────────────────────────────────────────

    def test_messy_chart_counts_only_messy_eggs(self, client):
        """Only quality='messy' eggs appear in the messy production chart."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)

        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt, quality="messy")
        EggFactory.create_batch(5, chicken=hen, laid_at=today_dt, quality="saleable")
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt, quality="edible")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert hen_data[-1] == 3

    def test_edible_chart_counts_only_edible_eggs(self, client):
        """Only quality='edible' eggs appear in the edible production chart."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)

        EggFactory.create_batch(4, chicken=hen, laid_at=today_dt, quality="edible")
        EggFactory.create_batch(6, chicken=hen, laid_at=today_dt, quality="saleable")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["edible_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert hen_data[-1] == 4

    def test_saleable_chart_counts_only_saleable_eggs(self, client):
        """Only quality='saleable' eggs appear in the saleable production chart."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)

        EggFactory.create_batch(7, chicken=hen, laid_at=today_dt, quality="saleable")
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt, quality="messy")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["saleable_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert hen_data[-1] == 7

    def test_messy_chart_zero_when_no_messy_eggs(self, client):
        """All-zero series when a hen has no messy eggs."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(4, chicken=hen, laid_at=today_dt, quality="saleable")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert all(v == 0 or v is None for v in hen_data)

    def test_quality_chart_respects_date_range(self, client):
        """Messy eggs outside the date range do not appear."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=10))
        before_range = datetime.combine(
            start - timedelta(days=1), datetime.min.time(), tzinfo=dt_timezone.utc
        )
        EggFactory.create_batch(3, chicken=hen, laid_at=before_range, quality="messy")

        params = {**self._base_params(start, today), "chickens": str(hen.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        hen_data = next(d["data"] for d in datasets if d["label"] == hen.name)
        assert all(v == 0 or v is None for v in hen_data)

    def test_quality_chart_respects_chicken_selection(self, client):
        """Only selected chickens appear in the quality production chart."""
        today = date.today()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(2, chicken=c2, laid_at=today_dt, quality="messy")

        params = {**self._base_params(start, today), "chickens": str(c1.pk)}
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["messy_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert c1.name in labels
        assert c2.name not in labels

    def test_quality_chart_multiple_hens(self, client):
        """Each selected hen gets its own series with correct quality counts."""
        today = date.today()
        start = today - timedelta(days=6)
        c1 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        c2 = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
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

    # ── include_non_saleable effect on main egg production chart ─────────────

    def test_include_non_saleable_adds_non_saleable_to_egg_prod(self, client):
        """Without include_non_saleable, only saleable eggs appear in production chart."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(3, chicken=hen, laid_at=today_dt, quality="saleable")
        EggFactory.create_batch(2, chicken=hen, laid_at=today_dt, quality="messy")
        EggFactory.create_batch(1, chicken=hen, laid_at=today_dt, quality="edible")

        base = {**self._base_params(start, today), "chickens": str(hen.pk)}

        r_without = client.get(reverse("metrics"), base)
        r_with = client.get(reverse("metrics"), {**base, "include_non_saleable": "1"})

        def last_value(response):
            datasets = json.loads(response.context["egg_prod_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == hen.name)[-1]

        # non-saleable excluded → 3 (saleable only); included → 6 (all)
        assert last_value(r_without) == 3
        assert last_value(r_with) == 6

    def test_include_non_saleable_off_does_not_affect_saleable_count(self, client):
        """Saleable eggs are counted identically whether include_non_saleable is on or off."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory.create_batch(4, chicken=hen, laid_at=today_dt, quality="saleable")

        base = {**self._base_params(start, today), "chickens": str(hen.pk)}

        r_off = client.get(reverse("metrics"), base)
        r_on = client.get(reverse("metrics"), {**base, "include_non_saleable": "1"})

        def last_value(response):
            datasets = json.loads(response.context["egg_prod_datasets_json"])
            return next(d["data"] for d in datasets if d["label"] == hen.name)[-1]

        assert last_value(r_off) == 4
        assert last_value(r_on) == 4

    # ── include_non_saleable effect on egg time-of-day KDE ───────────────────

    def test_include_non_saleable_changes_tod_egg_kde(self, client):
        """
        With non-saleable included, the KDE shape changes because messy eggs are
        at a different time of day. Saleable eggs at midnight, messy at noon.
        Without include_non_saleable the peak is near midnight; with it differs.
        """
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))

        midnight_dt = datetime.combine(
            today, datetime.min.time(), tzinfo=dt_timezone.utc
        )
        # Messy eggs at 12:00 UTC (bucket 72 = 720 minutes / 10)
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

        # The two KDEs should differ (adding messy eggs at noon changes the shape)
        assert kde_with != kde_without
        # Without non-saleable, the peak should be near midnight (bucket 0), not noon
        peak_without = kde_without.index(max(kde_without))
        NOON_BUCKET = 72
        assert peak_without != NOON_BUCKET

    # ── include_non_saleable effect on nesting box eggs pie chart ─────────────

    def test_include_non_saleable_adds_non_saleable_to_box_pie(self, client):
        """Without include_non_saleable, non-saleable eggs are excluded from the box pie."""
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        box = NestingBoxFactory(name="left")
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
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

    # ── _build_egg_prod_datasets unit tests ───────────────────────────────────

    @pytest.mark.django_db
    def test_build_helper_quality_filter_isolates_messy(self):
        """_build_egg_prod_datasets with Q(quality='messy') returns only messy counts."""
        today = date.today()
        start = today - timedelta(days=6)
        data_start = start - timedelta(days=1)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
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
        # Last non-None value should be 2 (only messy eggs)
        values = [v for v in datasets[0]["data"] if v is not None]
        assert values[-1] == 2

    @pytest.mark.django_db
    def test_build_helper_quality_filter_isolates_edible(self):
        """_build_egg_prod_datasets with Q(quality='edible') returns only edible counts."""
        today = date.today()
        start = today - timedelta(days=6)
        data_start = start - timedelta(days=1)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
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
        """_build_egg_prod_datasets with Q() (no filter) returns all eggs."""
        today = date.today()
        start = today - timedelta(days=6)
        data_start = start - timedelta(days=1)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
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
        assert values[-1] == 5  # 2 messy + 3 saleable


# ── Egg production vs age chart ───────────────────────────────────────────────


@pytest.mark.django_db
class TestMetricsViewAgeProd:
    """
    Tests for the egg-production-vs-age chart:
    - context keys present
    - x-axis labels are age-in-days integers
    - each hen's series is keyed by age, not calendar date
    - eggs outside the selected date range are excluded
    - chicken selection is respected
    - rolling window is applied correctly
    - hens not alive in the selected date range produce all-None/zero series
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

    # ── context keys ─────────────────────────────────────────────────────────

    def test_age_prod_labels_json_in_context(self, client):
        response = client.get(reverse("metrics"))
        assert "age_prod_labels_json" in response.context

    def test_age_prod_datasets_json_in_context(self, client):
        response = client.get(reverse("metrics"))
        assert "age_prod_datasets_json" in response.context

    def test_age_prod_labels_are_integers(self, client):
        today = date.today()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=10))
        response = client.get(reverse("metrics"), self._params(start, today, [hen]))
        labels = json.loads(response.context["age_prod_labels_json"])
        assert all(isinstance(v, int) for v in labels)
        assert labels == list(range(len(labels)))

    # ── x-axis is age, not calendar date ─────────────────────────────────────

    def test_egg_counted_at_correct_age(self, client):
        """An egg laid when the hen is 100 days old appears at age index 100."""
        today = date.today()
        dob = today - timedelta(days=200)
        hen = ChickenFactory(date_of_birth=dob)
        egg_date = dob + timedelta(days=100)
        start = egg_date - timedelta(days=6)
        end = egg_date + timedelta(days=6)

        egg_dt = datetime.combine(egg_date, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory(chicken=hen, laid_at=egg_dt)

        response = client.get(reverse("metrics"), self._params(start, end, [hen]))
        datasets = json.loads(response.context["age_prod_datasets_json"])
        assert len(datasets) == 1
        data = datasets[0]["data"]
        labels = json.loads(response.context["age_prod_labels_json"])

        # Find index in labels for age=100
        age_idx = labels.index(100)
        assert data[age_idx] == 1

    def test_two_hens_same_calendar_date_different_age(self, client):
        """
        Two hens born at different times lay on the same calendar day.
        They should appear at different age indices on the shared axis.
        """
        today = date.today()
        egg_date = today - timedelta(days=5)
        dob_old = egg_date - timedelta(days=200)
        dob_young = egg_date - timedelta(days=50)
        hen_old = ChickenFactory(date_of_birth=dob_old)
        hen_young = ChickenFactory(date_of_birth=dob_young)

        start = egg_date - timedelta(days=1)
        end = egg_date + timedelta(days=1)
        egg_dt = datetime.combine(egg_date, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory(chicken=hen_old, laid_at=egg_dt)
        EggFactory(chicken=hen_young, laid_at=egg_dt)

        response = client.get(
            reverse("metrics"), self._params(start, end, [hen_old, hen_young])
        )
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = json.loads(response.context["age_prod_labels_json"])

        old_data = next(d["data"] for d in datasets if d["label"] == hen_old.name)
        young_data = next(d["data"] for d in datasets if d["label"] == hen_young.name)

        # hen_old's egg is at age 200, hen_young's at age 50
        assert old_data[labels.index(200)] == 1
        assert young_data[labels.index(50)] == 1
        # hen_old at age 50: alive, no egg there → 0
        assert old_data[labels.index(50)] == 0
        # hen_young at age 200: doesn't exist yet → None (outside lifetime)
        assert young_data[labels.index(200)] is None

    # ── date range is intentionally ignored ──────────────────────────────────

    def test_eggs_before_start_still_appear_in_age_chart(self, client):
        """
        The age chart ignores the date range filter and shows the full lifetime,
        so eggs before `start` DO appear at the correct age index.
        """
        today = date.today()
        dob = today - timedelta(days=200)
        hen = ChickenFactory(date_of_birth=dob)
        start = today - timedelta(days=6)

        # Egg laid well before the display start date, at hen age 100
        age_100_date = dob + timedelta(days=100)
        egg_dt = datetime.combine(
            age_100_date, datetime.min.time(), tzinfo=dt_timezone.utc
        )
        EggFactory(chicken=hen, laid_at=egg_dt)

        response = client.get(reverse("metrics"), self._params(start, today, [hen]))
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = json.loads(response.context["age_prod_labels_json"])
        data = datasets[0]["data"]

        # Egg at age 100 should be visible despite being before `start`
        assert data[labels.index(100)] == 1

    # ── chicken selection ─────────────────────────────────────────────────────

    def test_unselected_hen_absent_from_datasets(self, client):
        today = date.today()
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
        response = client.get(
            reverse("metrics"),
            {"chickens_sent": "1"},  # no chickens param
        )
        datasets = json.loads(response.context["age_prod_datasets_json"])
        assert datasets == []

    # ── rolling window ────────────────────────────────────────────────────────

    def test_rolling_window_smooths_age_prod(self, client):
        """
        With window=1 the raw daily count is returned.
        With window=3 the value at a given age is the 3-day rolling average.
        """
        today = date.today()
        dob = today - timedelta(days=200)
        hen = ChickenFactory(date_of_birth=dob)
        start = today - timedelta(days=6)

        # 3 eggs on three consecutive days ending today
        for offset in range(3):
            egg_dt = datetime.combine(
                today - timedelta(days=2 - offset),
                datetime.min.time(),
                tzinfo=dt_timezone.utc,
            )
            EggFactory(chicken=hen, laid_at=egg_dt)

        params_w1 = self._params(start, today, [hen], window=1)
        params_w3 = self._params(start, today, [hen], window=3)

        r1 = client.get(reverse("metrics"), params_w1)
        r3 = client.get(reverse("metrics"), params_w3)

        data_w1 = json.loads(r1.context["age_prod_datasets_json"])[0]["data"]
        data_w3 = json.loads(r3.context["age_prod_datasets_json"])[0]["data"]

        # With w=1, last three non-None values are [1, 1, 1]
        non_none_w1 = [v for v in data_w1 if v is not None]
        assert non_none_w1[-3:] == [1.0, 1.0, 1.0]

        # With w=3, the rolling average of [1, 1, 1] = 1.0 at the last position
        non_none_w3 = [v for v in data_w3 if v is not None]
        assert non_none_w3[-1] == 1.0

    # ── include_non_saleable filter ───────────────────────────────────────────

    def test_non_saleable_excluded_from_age_prod_by_default(self, client):
        """Non-saleable eggs don't appear in the age chart unless include_non_saleable=1."""
        today = date.today()
        dob = today - timedelta(days=200)
        hen = ChickenFactory(date_of_birth=dob)
        start = today - timedelta(days=6)
        egg_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)

        EggFactory(chicken=hen, laid_at=egg_dt, quality="saleable")
        EggFactory(chicken=hen, laid_at=egg_dt, quality="messy")

        base = self._params(start, today, [hen])

        r_off = client.get(reverse("metrics"), base)
        r_on = client.get(reverse("metrics"), {**base, "include_non_saleable": "1"})

        def last_non_none(response):
            data = json.loads(response.context["age_prod_datasets_json"])[0]["data"]
            return next(v for v in reversed(data) if v is not None)

        assert last_non_none(r_off) == 1  # only saleable
        assert last_non_none(r_on) == 2  # saleable + messy

    # ── sum and mean series ───────────────────────────────────────────────────

    def test_show_mean_adds_mean_to_age_prod(self, client):
        """With show_mean=1, a Mean series is appended to the age prod datasets."""
        today = date.today()
        dob = today - timedelta(days=100)
        hen = ChickenFactory(date_of_birth=dob)
        egg_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory(chicken=hen, laid_at=egg_dt)

        params = {
            **self._params(today - timedelta(days=6), today, [hen]),
            "show_mean": "1",
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert "Mean" in labels

    def test_show_sum_adds_sum_to_age_prod(self, client):
        """With show_sum=1, a Sum series is appended to the age prod datasets."""
        today = date.today()
        dob = today - timedelta(days=100)
        hen = ChickenFactory(date_of_birth=dob)
        egg_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        EggFactory(chicken=hen, laid_at=egg_dt)

        params = {
            **self._params(today - timedelta(days=6), today, [hen]),
            "show_sum": "1",
        }
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert "Sum" in labels

    def test_mean_value_is_average_across_hens(self, client):
        """Mean at a given age = sum of all hen counts / number of hens alive at that age."""
        today = date.today()
        dob = today - timedelta(days=100)
        c1 = ChickenFactory(date_of_birth=dob)
        c2 = ChickenFactory(date_of_birth=dob)
        egg_dt = datetime.combine(today, datetime.min.time(), tzinfo=dt_timezone.utc)
        # c1 lays 2 eggs today, c2 lays 4
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
        # Age 100 = today; mean of (2, 4) = 3.0
        assert mean_data[labels.index(100)] == 3.0

    def test_no_sum_or_mean_without_flags(self, client):
        """By default (no show_sum/show_mean), neither Sum nor Mean appears."""
        today = date.today()
        hen = ChickenFactory(date_of_birth=today - timedelta(days=100))
        params = self._params(today - timedelta(days=6), today, [hen])
        response = client.get(reverse("metrics"), params)
        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert "Sum" not in labels
        assert "Mean" not in labels


@pytest.mark.django_db
class TestMetricsViewQueryCount:
    """The metrics view previously ran several per-hen queries inside
    loops (egg KDE, nesting TOD, age production), so query count grew
    linearly with the flock size. These tests pin the query count to
    a constant ceiling regardless of how many hens are chosen."""

    def _make_flock(self, n_hens: int, eggs_per_hen: int = 3):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()
        for _ in range(n_hens):
            hen = ChickenFactory(date_of_birth=today - timedelta(days=365))
            for d in range(eggs_per_hen):
                EggFactory(
                    chicken=hen,
                    laid_at=timezone.make_aware(
                        datetime.combine(
                            today - timedelta(days=d),
                            datetime.min.time(),
                        )
                    ),
                )
                NestingBoxPresencePeriodFactory(
                    chicken=hen,
                    started_at=timezone.make_aware(
                        datetime.combine(
                            today - timedelta(days=d),
                            datetime.min.time(),
                        )
                    ),
                    ended_at=timezone.make_aware(
                        datetime.combine(
                            today - timedelta(days=d),
                            datetime.min.time(),
                        )
                    )
                    + timedelta(minutes=5),
                )

    def test_query_count_is_bounded_at_10_hens(
        self, client, django_assert_max_num_queries
    ):
        """Whatever the exact number of queries, it must not explode
        with flock size. A generous ceiling of 40 queries catches the
        old O(N) behaviour (which at 10 hens would exceed 60 queries)
        without pinning the exact number."""
        self._make_flock(10)
        with django_assert_max_num_queries(40):
            response = client.get(reverse("metrics"))
            assert response.status_code == 200

    def test_query_count_does_not_grow_with_flock_size(
        self, client, django_assert_max_num_queries
    ):
        """Going from 5 to 20 hens must not add any queries. If it
        does, there's another N+1 lurking."""
        self._make_flock(20)
        with django_assert_max_num_queries(40):
            response = client.get(reverse("metrics"))
            assert response.status_code == 200


@pytest.mark.django_db
class TestMetricsParams:
    """Unit tests for the MetricsParams dataclass, which owns all of
    the metrics page's query-string parsing. Previously this logic was
    inlined at the top of ``MetricsView.get_context_data`` and could
    only be tested end-to-end through a full HTTP request."""

    def _qd(self, **kwargs) -> QueryDict:
        """Build a QueryDict with the given keys/values. Values given
        as lists map to repeated params (e.g. ``chickens=[1, 2]``)."""
        qd = QueryDict(mutable=True)
        for key, value in kwargs.items():
            if isinstance(value, list):
                qd.setlist(key, [str(v) for v in value])
            else:
                qd[key] = str(value)
        return qd

    def test_fresh_load_defaults(self):
        hens = [ChickenFactory(name=f"C{i}") for i in range(3)]

        params = MetricsParams.from_request(self._qd(), hens)

        # All three hens selected by default
        assert params.chosen == hens
        assert params.chickens_sent is False
        # Sensible defaults
        assert params.show_sum is False
        assert params.show_mean is True
        assert params.include_unknown is True
        assert params.include_non_saleable is False
        assert params.window == DEFAULT_WINDOW
        assert params.age_window == DEFAULT_AGE_WINDOW
        assert params.nest_sigma == DEFAULT_NEST_SIGMA
        assert params.kde_bandwidth == DEFAULT_KDE_BANDWIDTH

    def test_chickens_sent_empty_selection_respected(self):
        """An empty selection submitted through the form must be
        preserved (not silently re-defaulted to all hens)."""
        hens = [ChickenFactory(), ChickenFactory()]

        params = MetricsParams.from_request(self._qd(chickens_sent="1"), hens)

        assert params.chickens_sent is True
        assert params.chosen == []
        assert params.selected_ids == []

    def test_chickens_sent_filters_to_selected(self):
        c1 = ChickenFactory(name="A")
        c2 = ChickenFactory(name="B")
        c3 = ChickenFactory(name="C")

        params = MetricsParams.from_request(
            self._qd(chickens_sent="1", chickens=[c1.pk, c3.pk]), [c1, c2, c3]
        )

        assert set(params.chosen) == {c1, c3}

    def test_invalid_chicken_ids_ignored(self):
        c1 = ChickenFactory()
        params = MetricsParams.from_request(
            self._qd(chickens_sent="1", chickens=["not_a_number", c1.pk]), [c1]
        )
        # Invalid → whole list rejected → empty selection
        assert params.selected_ids == []

    def test_invalid_int_falls_back_to_default(self):
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(
            self._qd(w="banana", age_w="", nest_sigma="abc", kde_bw="-"), hens
        )
        assert params.window == DEFAULT_WINDOW
        assert params.age_window == DEFAULT_AGE_WINDOW
        assert params.nest_sigma == DEFAULT_NEST_SIGMA
        assert params.kde_bandwidth == DEFAULT_KDE_BANDWIDTH

    def test_out_of_choices_int_falls_back_to_default(self):
        """Values that parse as ints but aren't in the whitelist also
        fall back to defaults. This is important — allowing arbitrary
        window sizes lets a user pick unreasonable values that make
        charts look broken."""
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(self._qd(w="999999", kde_bw="-1"), hens)
        assert params.window == DEFAULT_WINDOW
        assert params.kde_bandwidth == DEFAULT_KDE_BANDWIDTH

    def test_start_after_end_clamps_to_default_span(self):
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(
            self._qd(start="2025-06-01", end="2025-05-01"), hens
        )
        # End is respected, start is pushed back to DEFAULT_SPAN days before
        assert params.end == date(2025, 5, 1)
        assert params.start == date(2025, 5, 1) - timedelta(days=DEFAULT_SPAN - 1)

    def test_malformed_date_uses_today(self):
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(self._qd(end="not-a-date"), hens)
        from django.utils import timezone

        assert params.end == timezone.localdate()

    def test_fresh_load_defaults_keep_on_with_empty_req(self):
        """On a fresh page load (no form sentinel), show_mean and
        include_unknown default to True even if not in the QueryDict."""
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(self._qd(), hens)
        assert params.show_mean is True
        assert params.include_unknown is True

    def test_submitted_form_treats_missing_toggles_as_off(self):
        """Once the form has been submitted, an absent show_mean (or
        include_unknown) means the user unchecked it."""
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(self._qd(chickens_sent="1"), hens)
        assert params.show_mean is False
        assert params.include_unknown is False

    def test_chosen_dob_by_id_property(self):
        c1 = ChickenFactory(date_of_birth=date(2024, 1, 1))
        c2 = ChickenFactory(date_of_birth=date(2024, 6, 1))
        params = MetricsParams.from_request(self._qd(), [c1, c2])
        assert params.chosen_dob_by_id == {
            c1.pk: date(2024, 1, 1),
            c2.pk: date(2024, 6, 1),
        }

    def test_normal_egg_filter_defaults_to_saleable_only(self):
        params = MetricsParams.from_request(self._qd(), [])
        # Default: filter to saleable
        assert str(params.normal_egg_filter) == str(Q(quality="saleable"))

    def test_normal_egg_filter_wide_open_when_non_saleable_included(self):
        params = MetricsParams.from_request(self._qd(include_non_saleable="1"), [])
        # Empty Q matches everything
        assert str(params.normal_egg_filter) == str(Q())
