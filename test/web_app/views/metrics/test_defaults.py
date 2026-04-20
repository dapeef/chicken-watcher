import json
from datetime import UTC, date, timedelta

import pytest
from django.urls import reverse

from test.web_app.factories import ChickenFactory
from web_app.views.metrics import (
    DEFAULT_AGE_WINDOW,
    DEFAULT_KDE_BANDWIDTH,
    DEFAULT_NEST_SIGMA,
    DEFAULT_SPAN,
    DEFAULT_WINDOW,
)


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

    def test_chickens_sent_empty_selection_still_shows_full_flock_count(self, client):
        """The flock size chart is always scoped to all chickens, not the
        current selection — even when no chickens are selected it shows
        the real headcount, not zeros."""
        ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1"})
        flock = json.loads(response.context["flock_count_dataset_json"])
        assert any(v > 0 for v in flock["data"])

    def test_invalid_chicken_id_ignored(self, client):
        c1 = ChickenFactory()
        url = reverse("metrics")
        response = client.get(url, {"chickens_sent": "1", "chickens": [str(c1.pk), "99999"]})
        assert response.status_code == 200
        datasets = json.loads(response.context["egg_prod_datasets_json"])
        labels = {d["label"] for d in datasets}
        assert c1.name in labels


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
        response = client.get(reverse("metrics"), {"start": "not-a-date", "end": "also-not"})
        end = date.fromisoformat(response.context["end"])
        start = date.fromisoformat(response.context["start"])
        assert (end - start).days == DEFAULT_SPAN - 1

    def test_start_after_end_falls_back_to_default_range(self, client):
        from django.utils import timezone

        today = timezone.localdate()
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
        from datetime import datetime

        from django.utils import timezone

        today = timezone.localdate()
        start = today - timedelta(days=6)
        hen = ChickenFactory(date_of_birth=start - timedelta(days=1))
        today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        from test.web_app.factories import EggFactory

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

        peak_narrow = max(datasets_narrow[0]["data"])
        peak_wide = max(datasets_wide[0]["data"])
        assert peak_narrow > peak_wide
