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

        response = client.get(reverse("metrics"), self._params(start, end, [hen_old, hen_young]))
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
        egg_dt = datetime.combine(age_100_date, datetime.min.time(), tzinfo=UTC)
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

    def test_default_age_window_is_30(self, client):
        """Regression: default was 14 days, changed to 30."""
        from web_app.views.metrics import DEFAULT_AGE_WINDOW

        assert DEFAULT_AGE_WINDOW == 30

        response = client.get(reverse("metrics"))
        assert response.context["age_window"] == 30

    def test_rolling_average_is_centered_not_right_shifted(self, client):
        """The age-production rolling average must be centered, meaning the
        smoothed value at age ``i`` uses data from ``[i - w//2, i + w//2]``.

        With RIGHT alignment (the old behaviour), the smoothed value at age
        ``i`` was the mean of data from ``[i - w + 1, i]``. This meant:
        - The smoothed value at the egg's age was non-zero (it's always the
          *end* of a window that contains the egg).
        - But the first non-zero smoothed value appeared ``w - 1`` days
          *before* the egg age (day egg_age - (w-1)).

        With CENTER alignment:
        - The smoothed value at the egg's age is also non-zero.
        - The first non-zero value appears ``w//2`` days before the egg age.
        - The last non-zero value appears ``w//2`` days *after* the egg age,
          which means the curve is symmetric around the true egg age.

        We verify the symmetric property: with a single egg at a known age,
        the smoothed series must be non-zero both ``w//2`` days before AND
        ``w//2`` days after the egg age. Under right-shift, the series is
        only non-zero before the egg age (never after), so this test would
        fail under the old code.
        """
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=300)
        egg_age = 150
        egg_date = dob + timedelta(days=egg_age)
        hen = ChickenFactory(date_of_birth=dob)
        EggFactory(
            chicken=hen,
            laid_at=datetime.combine(egg_date, datetime.min.time(), tzinfo=UTC),
        )

        # Use age_w=30 (a valid WINDOW_CHOICES value).
        start = egg_date - timedelta(days=10)
        end = egg_date + timedelta(days=10)
        params = {**self._params(start, end, [hen], window=30)}
        response = client.get(reverse("metrics"), params)

        datasets = json.loads(response.context["age_prod_datasets_json"])
        labels = json.loads(response.context["age_prod_labels_json"])
        data = datasets[0]["data"]

        # Build a mapping age → smoothed value for easy lookup.
        smoothed = {labels[i]: v for i, v in enumerate(data)}

        # rolling_average CENTER uses window_before = ceil(w/2) - 1 and
        # window_after = floor(w/2). For w=30: window_before=14, window_after=15.
        # The window centered at position i spans [i-14 .. i+15].
        # → the last position whose window includes the egg at egg_age is
        #   i = egg_age + window_before = egg_age + 14.
        # → the first position whose window includes the egg is
        #   i = egg_age - window_after = egg_age - 15.
        from math import ceil, floor

        w = 30
        window_before = ceil(w / 2) - 1  # = 14
        window_after = floor(w / 2)  # = 15

        # Non-zero before the egg age (true for both CENTER and RIGHT).
        before_age = egg_age - window_after  # first position with egg in window
        assert smoothed.get(before_age) is not None and smoothed[before_age] > 0, (
            f"Expected non-zero smoothed value at age {before_age} "
            f"({window_after} days before egg age {egg_age})"
        )

        # Non-zero AFTER the egg age — only true for CENTER, not RIGHT.
        # Under right-shift the window at (egg_age + 1) would not contain
        # the egg, so its smoothed value would be 0.
        after_age = egg_age + window_before  # last position with egg in window
        assert smoothed.get(after_age) is not None and smoothed[after_age] > 0, (
            f"Expected non-zero smoothed value at age {after_age} "
            f"({window_before} days after egg age {egg_age}). "
            "If this is 0 or None, the rolling average is right-shifted, not centered."
        )
