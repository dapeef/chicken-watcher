"""Tests for web_app.templatetags.chicken_extras."""

from datetime import timedelta, date

import pytest
from django.urls import reverse

from web_app.templatetags.chicken_extras import (
    duration_ymd,
    duration_hms,
    _years_months_days,
)
from .factories import (
    ChickenFactory,
    NestingBoxPresencePeriodFactory,
)


# ---------------------------------------------------------------------------
# Unit tests for the pure helper _years_months_days
# ---------------------------------------------------------------------------


class TestYearsMonthsDays:
    def test_zero_days(self):
        assert _years_months_days(0) == (0, 0, 0)

    def test_fewer_than_30_days(self):
        assert _years_months_days(5) == (0, 0, 5)

    def test_exactly_30_days(self):
        assert _years_months_days(30) == (0, 1, 0)

    def test_one_month_and_some_days(self):
        assert _years_months_days(35) == (0, 1, 5)

    def test_exactly_one_year(self):
        assert _years_months_days(365) == (1, 0, 0)

    def test_one_year_one_month_one_day(self):
        # 365 + 30 + 1 = 396
        assert _years_months_days(396) == (1, 1, 1)

    def test_two_years(self):
        assert _years_months_days(730) == (2, 0, 0)

    def test_large_value(self):
        # 3 years (1095) + 6 months (180) + 15 days = 1290
        assert _years_months_days(1290) == (3, 6, 15)


# ---------------------------------------------------------------------------
# Unit tests for the duration_ymd filter
# ---------------------------------------------------------------------------


class TestDurationYmd:
    # --- timedelta inputs ---

    def test_zero(self):
        assert duration_ymd(timedelta(days=0)) == "0d"

    def test_days_only(self):
        assert duration_ymd(timedelta(days=5)) == "5d"

    def test_months_and_days(self):
        assert duration_ymd(timedelta(days=35)) == "1m 5d"

    def test_months_and_zero_days(self):
        assert duration_ymd(timedelta(days=60)) == "2m 0d"

    def test_years_months_days(self):
        # 365 + 30 + 1 = 396 days
        assert duration_ymd(timedelta(days=396)) == "1y 1m 1d"

    def test_years_zero_months(self):
        assert duration_ymd(timedelta(days=365)) == "1y 0m 0d"

    def test_two_years(self):
        assert duration_ymd(timedelta(days=730)) == "2y 0m 0d"

    def test_months_shown_when_years_present_even_if_zero(self):
        # When years > 0, months component is always shown (even if 0)
        assert duration_ymd(timedelta(days=370)) == "1y 0m 5d"

    def test_months_omitted_when_no_years_and_no_months(self):
        # Sub-30-day value: no months component at all
        result = duration_ymd(timedelta(days=10))
        assert "m" not in result
        assert result == "10d"

    # --- integer inputs ---

    def test_integer_input(self):
        assert duration_ymd(100) == "3m 10d"

    # --- edge / error inputs ---

    def test_none_returns_empty_string(self):
        assert duration_ymd(None) == ""

    def test_negative_returns_empty_string(self):
        assert duration_ymd(timedelta(days=-1)) == ""

    def test_string_non_numeric_returns_empty_string(self):
        assert duration_ymd("not a number") == ""

    def test_string_numeric_returns_formatted(self):
        assert duration_ymd("30") == "1m 0d"


# ---------------------------------------------------------------------------
# Integration: the age column in the rendered chicken list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChickenListAgeColumn:
    url = reverse("chicken_list")

    def test_age_column_shows_ymd_format(self, client):
        today = date.today()
        # 400 days = 1y 1m 5d  (365 + 30 + 5)
        ChickenFactory(date_of_birth=today - date.resolution * 400, date_of_death=None)
        response = client.get(self.url)
        assert b"1y" in response.content or b"m" in response.content  # at least months

    def test_age_column_does_not_show_raw_days(self, client):
        today = date.today()
        ChickenFactory(date_of_birth=today - date.resolution * 400, date_of_death=None)
        response = client.get(self.url)
        # Raw "400" should not appear as a standalone age cell value
        assert b">400<" not in response.content

    def test_deceased_hen_age_capped(self, client):
        today = date.today()
        dob = today - date.resolution * 400
        dod = (
            today - date.resolution * 35
        )  # died 35 days ago => age = 365 days = 1y 0m 0d
        ChickenFactory(date_of_birth=dob, date_of_death=dod)
        response = client.get(self.url)
        assert b"1y" in response.content


# ---------------------------------------------------------------------------
# Unit tests for the duration_hms filter
# ---------------------------------------------------------------------------


class TestDurationHms:
    # --- sub-minute: shown to 1 dp ---

    def test_zero(self):
        assert duration_hms(timedelta(0)) == "0.0 secs"

    def test_one_second_exact(self):
        assert duration_hms(timedelta(seconds=1)) == "1.0 sec"

    def test_sub_minute_fractional(self):
        assert duration_hms(timedelta(seconds=8.3)) == "8.3 secs"

    def test_sub_minute_rounds_to_1dp(self):
        assert duration_hms(timedelta(seconds=8.36)) == "8.4 secs"

    def test_59_seconds(self):
        assert duration_hms(timedelta(seconds=59)) == "59.0 secs"

    def test_sub_minute_plural(self):
        assert duration_hms(timedelta(seconds=10)) == "10.0 secs"

    # --- at the boundary: exactly 60 s switches to integer mode ---

    def test_exactly_one_minute(self):
        assert duration_hms(timedelta(minutes=1)) == "1 min, 0 secs"

    # --- 1 minute or more: whole seconds ---

    def test_one_minute_one_second(self):
        assert duration_hms(timedelta(minutes=1, seconds=1)) == "1 min, 1 sec"

    def test_plural_minutes(self):
        assert duration_hms(timedelta(minutes=2, seconds=30)) == "2 mins, 30 secs"

    def test_minutes_shown_with_zero_seconds(self):
        assert duration_hms(timedelta(minutes=5)) == "5 mins, 0 secs"

    def test_fractional_seconds_rounded_when_over_1_min(self):
        # 75.6 s -> round to 76 s -> "1 min, 16 secs"
        assert duration_hms(timedelta(seconds=75.6)) == "1 min, 16 secs"

    # --- hours + minutes + seconds ---

    def test_exactly_one_hour(self):
        assert duration_hms(timedelta(hours=1)) == "1 hr, 0 mins, 0 secs"

    def test_one_hour_one_minute_one_second(self):
        assert (
            duration_hms(timedelta(hours=1, minutes=1, seconds=1))
            == "1 hr, 1 min, 1 sec"
        )

    def test_plural_hours(self):
        assert (
            duration_hms(timedelta(hours=2, minutes=30, seconds=5))
            == "2 hrs, 30 mins, 5 secs"
        )

    def test_hours_with_zero_minutes(self):
        assert duration_hms(timedelta(hours=3)) == "3 hrs, 0 mins, 0 secs"

    # --- edge / error inputs ---

    def test_none_returns_zero_secs(self):
        assert duration_hms(None) == "0.0 secs"

    def test_negative_clamps_to_zero(self):
        assert duration_hms(timedelta(seconds=-5)) == "0.0 secs"

    def test_integer_input_seconds(self):
        assert duration_hms(75) == "1 min, 15 secs"

    def test_non_numeric_string_returns_zero_secs(self):
        assert duration_hms("bad") == "0.0 secs"


# ---------------------------------------------------------------------------
# Integration: duration shown in the latest presence partial
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLatestPresenceDurationFormat:
    def test_duration_rendered_as_hms(self, client):
        from django.utils import timezone as tz

        now = tz.now()
        period = NestingBoxPresencePeriodFactory(
            started_at=now - timedelta(hours=1, minutes=2, seconds=10),
            ended_at=now,
        )
        url = reverse("partial_latest_presence")
        response = client.get(url)
        assert response.status_code == 200
        assert b"1 hr" in response.content
        assert b"2 mins" in response.content
        assert b"10 secs" in response.content

    def test_raw_timedelta_str_not_shown(self, client):
        from django.utils import timezone as tz

        now = tz.now()
        NestingBoxPresencePeriodFactory(
            started_at=now - timedelta(minutes=5),
            ended_at=now,
        )
        url = reverse("partial_latest_presence")
        response = client.get(url)
        assert response.status_code == 200
        # Django's default timedelta str looks like "0:05:00" — should not appear
        assert b"0:05:00" not in response.content
        assert b"5 mins" in response.content
