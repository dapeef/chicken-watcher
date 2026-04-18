from datetime import date, timedelta

import pytest
from django.db.models import Q
from django.http import QueryDict

from test.web_app.factories import ChickenFactory
from web_app.views.metrics import (
    DEFAULT_AGE_WINDOW,
    DEFAULT_KDE_BANDWIDTH,
    DEFAULT_NEST_SIGMA,
    DEFAULT_SPAN,
    DEFAULT_WINDOW,
    MetricsParams,
)


@pytest.mark.django_db
class TestMetricsParams:
    """Unit tests for the MetricsParams dataclass, which owns all of
    the metrics page's query-string parsing."""

    def _qd(self, **kwargs) -> QueryDict:
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

        assert params.chosen == hens
        assert params.chickens_sent is False
        assert params.show_sum is False
        assert params.show_mean is True
        assert params.include_unknown is True
        assert params.include_non_saleable is False
        assert params.window == DEFAULT_WINDOW
        assert params.age_window == DEFAULT_AGE_WINDOW
        assert params.nest_sigma == DEFAULT_NEST_SIGMA
        assert params.kde_bandwidth == DEFAULT_KDE_BANDWIDTH

    def test_chickens_sent_empty_selection_respected(self):
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
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(self._qd(w="999999", kde_bw="-1"), hens)
        assert params.window == DEFAULT_WINDOW
        assert params.kde_bandwidth == DEFAULT_KDE_BANDWIDTH

    def test_start_after_end_clamps_to_default_span(self):
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(self._qd(start="2025-06-01", end="2025-05-01"), hens)
        assert params.end == date(2025, 5, 1)
        assert params.start == date(2025, 5, 1) - timedelta(days=DEFAULT_SPAN - 1)

    def test_malformed_date_uses_today(self):
        from django.utils import timezone

        hens = [ChickenFactory()]
        params = MetricsParams.from_request(self._qd(end="not-a-date"), hens)
        assert params.end == timezone.localdate()

    def test_fresh_load_defaults_keep_on_with_empty_req(self):
        hens = [ChickenFactory()]
        params = MetricsParams.from_request(self._qd(), hens)
        assert params.show_mean is True
        assert params.include_unknown is True

    def test_submitted_form_treats_missing_toggles_as_off(self):
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
        assert str(params.normal_egg_filter) == str(Q(quality="saleable"))

    def test_normal_egg_filter_wide_open_when_non_saleable_included(self):
        params = MetricsParams.from_request(self._qd(include_non_saleable="1"), [])
        assert str(params.normal_egg_filter) == str(Q())
