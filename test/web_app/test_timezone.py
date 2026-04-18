"""
Tests verifying correct BST / UTC handling throughout the application.

The system stores all datetimes in UTC (Django's USE_TZ=True ensures this),
but TIME_ZONE = "Europe/London" means that:
  - Forms interpret naive local inputs as Europe/London time (BST in summer,
    GMT in winter).
  - Template filters display datetimes in Europe/London local time.
  - "Today" boundaries in the dashboard respect local midnight, not UTC midnight.

Key BST facts used in these tests:
  - BST is UTC+1 (clocks spring forward last Sunday of March, fall back last
    Sunday of October).
  - Example: 10:30 BST == 09:30 UTC.
  - Example: 23:30 BST on day D == 22:30 UTC on day D.
  - Example: 00:30 BST on day D == 23:30 UTC on day D-1.
"""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from web_app.forms import EggForm
from web_app.views.dashboard import get_dashboard_context

from .factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
)

LONDON = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")

# Concrete aware datetimes used across the tests
# A moment in BST (British Summer Time, UTC+1)
BST_10_30 = datetime(2025, 6, 15, 10, 30, tzinfo=LONDON)  # 09:30 UTC
BST_09_30_UTC = datetime(2025, 6, 15, 9, 30, tzinfo=UTC)  # same instant as above

# A moment in GMT (winter, UTC+0)
GMT_10_30 = datetime(2025, 1, 15, 10, 30, tzinfo=LONDON)  # 10:30 UTC
GMT_10_30_UTC = datetime(2025, 1, 15, 10, 30, tzinfo=UTC)  # same instant as above


# ---------------------------------------------------------------------------
# 1. EggForm – BST input stored correctly as UTC
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEggFormTimezone:
    """EggForm.clean_laid_at must interpret naive input as Europe/London local
    time and store it correctly as UTC in the database."""

    def _make_form_data(self, naive_str: str):
        chicken = ChickenFactory()
        box = NestingBoxFactory()
        return {
            "chicken": chicken.pk,
            "nesting_box": box.pk,
            "laid_at": naive_str,
        }

    def test_bst_time_stored_as_utc_minus_one_hour(self):
        """A time entered in BST (e.g. 10:30 on a summer date) must be stored
        as 09:30 UTC, not as 10:30 UTC."""
        data = self._make_form_data("2025-06-15T10:30")  # 10:30 BST
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()

        # The stored UTC value must be one hour earlier than the entered time
        assert egg.laid_at == BST_09_30_UTC, (
            f"Expected {BST_09_30_UTC} (09:30 UTC) but got {egg.laid_at} "
            f"({egg.laid_at.astimezone(LONDON)})"
        )

    def test_bst_time_is_timezone_aware(self):
        """The stored laid_at must always be timezone-aware (never naive)."""
        data = self._make_form_data("2025-06-15T10:30")
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()
        assert timezone.is_aware(egg.laid_at)

    def test_gmt_time_stored_unchanged_as_utc(self):
        """In winter (GMT == UTC), a time entered as 10:30 must be stored as
        10:30 UTC – no offset applied."""
        data = self._make_form_data("2025-01-15T10:30")  # 10:30 GMT == 10:30 UTC
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()

        assert egg.laid_at == GMT_10_30_UTC, (
            f"Expected {GMT_10_30_UTC} (10:30 UTC) but got {egg.laid_at}"
        )

    def test_bst_local_time_roundtrips_correctly(self):
        """Converting the stored UTC value back to London time must yield the
        original input time."""
        data = self._make_form_data("2025-06-15T10:30")  # 10:30 BST
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()

        local = egg.laid_at.astimezone(LONDON)
        assert local.hour == 10
        assert local.minute == 30

    def test_gmt_local_time_roundtrips_correctly(self):
        """Converting a winter-stored UTC value back to London time must also
        yield the original input time."""
        data = self._make_form_data("2025-01-15T10:30")  # 10:30 GMT
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()

        local = egg.laid_at.astimezone(LONDON)
        assert local.hour == 10
        assert local.minute == 30

    def test_bst_midnight_crossing(self):
        """An egg entered at 00:30 BST on a summer day must be stored as 23:30
        UTC on the *previous* calendar day."""
        data = self._make_form_data("2025-06-15T00:30")  # 00:30 BST = 23:30 UTC June 14
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()

        assert egg.laid_at.tzinfo is not None
        utc_time = egg.laid_at.astimezone(UTC)
        assert utc_time.day == 14, f"Expected UTC day 14, got {utc_time.day}"
        assert utc_time.hour == 23
        assert utc_time.minute == 30

    def test_bst_end_of_day(self):
        """An egg entered at 23:30 BST must be stored as 22:30 UTC on the same
        calendar day."""
        data = self._make_form_data("2025-06-15T23:30")  # 23:30 BST = 22:30 UTC
        form = EggForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()

        utc_time = egg.laid_at.astimezone(UTC)
        assert utc_time.day == 15
        assert utc_time.hour == 22
        assert utc_time.minute == 30

    def test_already_aware_value_not_double_offset(self):
        """If the cleaned value is already timezone-aware, clean_laid_at must
        not apply a second offset."""
        # Submitting a naive string is the normal browser path; this test guards
        # against any future code path that supplies an already-aware datetime.
        from web_app.forms import EggForm as _EggForm

        class PatchedForm(_EggForm):
            def clean_laid_at(self):
                # Simulate a pre-aware value reaching clean_laid_at
                aware = datetime(2025, 6, 15, 10, 30, tzinfo=UTC)
                self.cleaned_data["laid_at"] = aware
                return super().clean_laid_at()

        chicken = ChickenFactory()
        box = NestingBoxFactory()
        data = {
            "chicken": chicken.pk,
            "nesting_box": box.pk,
            "laid_at": "2025-06-15T10:30",
        }
        form = PatchedForm(data=data)
        assert form.is_valid(), form.errors
        egg = form.save()
        # Must still be 10:30 UTC – not shifted again
        assert egg.laid_at == datetime(2025, 6, 15, 10, 30, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 2. Template rendering – egg list displays BST times
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEggListTimezoneDisplay:
    """The egg list template must display laid_at in Europe/London local time,
    not in UTC."""

    def test_bst_egg_displayed_in_local_time(self, client):
        """An egg stored at 09:30 UTC (== 10:30 BST) must be shown as 10:30,
        not 09:30, on the egg list page."""
        from django.urls import reverse

        EggFactory(laid_at=BST_09_30_UTC)  # stored as 09:30 UTC
        url = reverse("egg_list")
        response = client.get(url)
        content = response.content.decode()

        # Should show 10:30 (BST local time), not 09:30 (raw UTC)
        assert "10:30" in content, (
            "Expected BST local time '10:30' in egg list but it was not found"
        )
        assert "09:30" not in content, (
            "UTC time '09:30' appeared in egg list – template is not converting "
            "to local time"
        )

    def test_gmt_egg_displayed_same_as_utc(self, client):
        """In winter (GMT == UTC) the displayed time must equal the stored UTC
        time, so there is no offset applied."""
        from django.urls import reverse

        EggFactory(laid_at=GMT_10_30_UTC)  # stored as 10:30 UTC == 10:30 GMT
        url = reverse("egg_list")
        response = client.get(url)
        content = response.content.decode()

        assert "10:30" in content

    def test_bst_egg_shows_correct_date(self, client):
        """An egg at 23:30 BST (22:30 UTC on the same calendar day) must show
        the BST date, not the UTC date."""
        from django.urls import reverse

        # 22:30 UTC on June 15 == 23:30 BST June 15
        laid_utc = datetime(2025, 6, 15, 22, 30, tzinfo=UTC)
        EggFactory(laid_at=laid_utc)
        url = reverse("egg_list")
        response = client.get(url)
        content = response.content.decode()

        # Local BST date is still June 15
        assert "2025-06-15" in content

    def test_bst_midnight_egg_shows_local_date(self, client):
        """An egg at 23:30 UTC on June 14 is 00:30 BST June 15. The list must
        show June 15, not June 14."""
        from django.urls import reverse

        # 23:30 UTC June 14 == 00:30 BST June 15
        laid_utc = datetime(2025, 6, 14, 23, 30, tzinfo=UTC)
        EggFactory(laid_at=laid_utc)
        url = reverse("egg_list")
        response = client.get(url)
        content = response.content.decode()

        assert "2025-06-15" in content, (
            "Expected BST date June 15 but it was not in the response"
        )
        assert "2025-06-14" not in content, (
            "UTC date June 14 appeared – template is using UTC date"
        )


# ---------------------------------------------------------------------------
# 3. Dashboard – "today" boundaries respect local midnight
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDashboardTimezone:
    """The dashboard counts eggs laid 'today'. 'Today' must be measured in
    Europe/London local time, not UTC."""

    def test_egg_at_bst_midnight_counted_as_today(self, mocker):
        """An egg laid just after local midnight (00:30 BST = 23:30 UTC the
        previous day) must be counted in today's total.

        We freeze 'now' to 08:00 BST on June 15. The egg at 00:30 BST June 15
        (= 23:30 UTC June 14) must appear in today's eggs.
        """
        # 'now' is 08:00 BST = 07:00 UTC on June 15
        fake_now = datetime(2025, 6, 15, 7, 0, tzinfo=UTC)
        mocker.patch(
            "web_app.views.dashboard.timezone.localtime",
            return_value=fake_now.astimezone(LONDON),
        )

        # Egg at 00:30 BST June 15 == 23:30 UTC June 14
        egg_utc = datetime(2025, 6, 14, 23, 30, tzinfo=UTC)
        EggFactory(laid_at=egg_utc)

        ctx = get_dashboard_context()
        assert ctx["eggs_today"] == 1, (
            "Egg laid at 00:30 BST (23:30 UTC previous day) must be counted "
            f"as today's egg, but eggs_today={ctx['eggs_today']}"
        )

    def test_egg_at_bst_midnight_would_be_missed_if_using_utc_boundary(self, mocker):
        """Demonstrates the bug that existed when TIME_ZONE was UTC: an egg at
        00:30 BST (23:30 UTC prev day) would NOT be counted as today because
        UTC midnight is one hour later than BST midnight.

        This test documents that with the fix in place the egg IS found.
        """
        # now = 07:00 UTC on June 15 (= 08:00 BST June 15)
        fake_now = datetime(2025, 6, 15, 7, 0, tzinfo=UTC)
        mocker.patch(
            "web_app.views.dashboard.timezone.localtime",
            return_value=fake_now.astimezone(LONDON),
        )

        # 23:30 UTC June 14 == 00:30 BST June 15 (just after local midnight)
        egg_utc = datetime(2025, 6, 14, 23, 30, tzinfo=UTC)
        EggFactory(laid_at=egg_utc)

        ctx = get_dashboard_context()
        # With the fix, this egg IS counted because today_start is BST midnight
        # (== 23:00 UTC June 14), which is before the egg's 23:30 UTC.
        assert ctx["eggs_today"] == 1

    def test_egg_yesterday_bst_not_counted_today(self, mocker):
        """An egg laid at 22:00 UTC on June 14 is 23:00 BST June 14, which is
        still yesterday in local time – it must NOT be counted today."""
        # now = 07:00 UTC June 15 (08:00 BST June 15)
        fake_now = datetime(2025, 6, 15, 7, 0, tzinfo=UTC)
        mocker.patch(
            "web_app.views.dashboard.timezone.localtime",
            return_value=fake_now.astimezone(LONDON),
        )

        # 22:00 UTC June 14 == 23:00 BST June 14 — still yesterday
        egg_utc = datetime(2025, 6, 14, 22, 0, tzinfo=UTC)
        EggFactory(laid_at=egg_utc)

        ctx = get_dashboard_context()
        assert ctx["eggs_today"] == 0, (
            "Egg from 23:00 BST yesterday must not be counted as today's egg"
        )

    def test_multiple_bst_eggs_today_all_counted(self, mocker):
        """Multiple eggs laid during BST today are all counted."""
        # now = 14:00 UTC June 15 (15:00 BST)
        fake_now = datetime(2025, 6, 15, 14, 0, tzinfo=UTC)
        mocker.patch(
            "web_app.views.dashboard.timezone.localtime",
            return_value=fake_now.astimezone(LONDON),
        )

        # 3 eggs all within BST today (between 23:00 UTC June 14 and now)
        EggFactory(
            laid_at=datetime(2025, 6, 14, 23, 30, tzinfo=UTC)
        )  # 00:30 BST June 15
        EggFactory(laid_at=datetime(2025, 6, 15, 7, 0, tzinfo=UTC))  # 08:00 BST June 15
        EggFactory(
            laid_at=datetime(2025, 6, 15, 11, 0, tzinfo=UTC)
        )  # 12:00 BST June 15

        ctx = get_dashboard_context()
        assert ctx["eggs_today"] == 3

    def test_gmt_midnight_boundary_unchanged(self, mocker):
        """In winter (GMT == UTC) the midnight boundary is unchanged: an egg
        at 23:50 UTC the previous day must not be counted today."""
        # now = 10:00 UTC Jan 15 (same as 10:00 GMT)
        fake_now = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        mocker.patch(
            "web_app.views.dashboard.timezone.localtime",
            return_value=fake_now.astimezone(LONDON),
        )

        # Egg at 23:50 UTC Jan 14 — still yesterday in GMT too
        egg_utc = datetime(2025, 1, 14, 23, 50, tzinfo=UTC)
        EggFactory(laid_at=egg_utc)

        ctx = get_dashboard_context()
        assert ctx["eggs_today"] == 0

    def test_gmt_today_egg_counted(self, mocker):
        """In winter an egg laid early this morning (UTC == GMT) is counted."""
        # now = 10:00 UTC Jan 15
        fake_now = datetime(2025, 1, 15, 10, 0, tzinfo=UTC)
        mocker.patch(
            "web_app.views.dashboard.timezone.localtime",
            return_value=fake_now.astimezone(LONDON),
        )

        egg_utc = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)  # 08:00 UTC Jan 15
        EggFactory(laid_at=egg_utc)

        ctx = get_dashboard_context()
        assert ctx["eggs_today"] == 1


# ---------------------------------------------------------------------------
# 4. Form initial value – pre-filled time is in local time, not UTC
# ---------------------------------------------------------------------------


class TestEggFormInitialValue:
    """The EggForm pre-fills laid_at with the current local time. When the
    server is configured as Europe/London, this initial value must reflect
    local time (BST in summer)."""

    def test_initial_laid_at_is_callable(self):
        """initial=timezone.localtime is a callable so Django evaluates it
        freshly on each form instantiation – not at module import time."""
        form = EggForm()
        # Access the field's initial value
        initial = form.fields["laid_at"].initial
        # It should be callable (timezone.localtime function) so Django calls
        # it at render time
        assert callable(initial), (
            "EggForm.laid_at.initial should be callable so it is evaluated "
            "at render time, not at import time"
        )

    def test_initial_value_is_timezone_localtime_function(self):
        """The EggForm.laid_at initial must be exactly django.utils.timezone.localtime
        so that Django calls it at render time to get the current London-local time.

        This is the key property: using timezone.localtime (not timezone.now)
        ensures the pre-filled time respects Europe/London (BST in summer),
        not raw UTC.
        """
        from django.utils import timezone as dj_timezone

        form = EggForm()
        assert form.fields["laid_at"].initial is dj_timezone.localtime, (
            "EggForm.laid_at.initial must be timezone.localtime so the pre-filled "
            "time is in local (Europe/London) time rather than UTC"
        )

    def test_initial_value_returns_local_timezone_aware_datetime(self):
        """Calling the initial callable must return a timezone-aware datetime
        whose timezone is Europe/London (BST or GMT depending on time of year)."""
        form = EggForm()
        initial_val = form.fields["laid_at"].initial()

        assert timezone.is_aware(initial_val), "Initial value must be timezone-aware"
        # The returned value must be in the London timezone
        tz_str = str(initial_val.tzinfo)
        assert tz_str == "Europe/London", (
            f"Initial value must be in Europe/London timezone, got '{tz_str}'"
        )


# ---------------------------------------------------------------------------
# 5. Settings verification
# ---------------------------------------------------------------------------


class TestTimezoneSettings:
    """Verify the Django settings are correct for Europe/London localisation."""

    def test_time_zone_is_europe_london(self):
        from django.conf import settings

        assert settings.TIME_ZONE == "Europe/London", (
            f"TIME_ZONE must be 'Europe/London', got '{settings.TIME_ZONE}'"
        )

    def test_use_tz_is_true(self):
        from django.conf import settings

        assert settings.USE_TZ is True, "USE_TZ must be True for timezone-aware storage"

    def test_get_current_timezone_is_london(self):
        """Django's get_current_timezone() must return Europe/London, which
        covers both GMT and BST automatically."""
        tz = timezone.get_current_timezone()
        assert str(tz) == "Europe/London", f"Expected 'Europe/London', got '{tz}'"

    def test_bst_offset_in_summer(self):
        """During BST (e.g. June), Europe/London is UTC+1."""
        london = ZoneInfo("Europe/London")
        summer_dt = datetime(2025, 6, 15, 12, 0, tzinfo=london)
        offset = summer_dt.utcoffset()
        assert offset is not None
        offset_hours = offset.total_seconds() / 3600
        assert offset_hours == 1.0, f"Expected UTC+1 in summer, got UTC+{offset_hours}"

    def test_gmt_offset_in_winter(self):
        """During GMT (e.g. January), Europe/London is UTC+0."""
        london = ZoneInfo("Europe/London")
        winter_dt = datetime(2025, 1, 15, 12, 0, tzinfo=london)
        offset = winter_dt.utcoffset()
        assert offset is not None
        offset_hours = offset.total_seconds() / 3600
        assert offset_hours == 0.0, f"Expected UTC+0 in winter, got UTC+{offset_hours}"


# ---------------------------------------------------------------------------
# 7. Chicken.age – must use local date, not UTC date
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChickenAgeTimezone:
    """Chicken.age must be calculated against the local date, not the UTC
    date. Using date.today() would return the UTC date, which can be a day
    behind (or ahead of) the local date near midnight.

    Scenario: at 00:30 BST on day D, UTC is still on day D-1 at 23:30.
    A chicken born on day D has an age of 0 days (local) or -1 days (UTC).
    """

    def test_age_at_bst_midnight_boundary_uses_local_date(self, mocker):
        """At 00:30 BST on 2025-06-16 (== 23:30 UTC on 2025-06-15), a chicken
        born on 2025-06-15 is 1 day old locally.

        This test verifies that Chicken.age uses timezone.localdate() (which
        respects TIME_ZONE=Europe/London) rather than the old implementation
        that used date.today() (which depends on the process's system clock).
        """
        # Fake "now" at 00:30 BST = 23:30 UTC the previous day. Django's
        # timezone.localdate() derives its date from timezone.now(), so
        # mocking the latter is sufficient.
        fake_utc_now = datetime(2025, 6, 15, 23, 30, tzinfo=UTC)
        mocker.patch(
            "django.utils.timezone.now",
            return_value=fake_utc_now,
        )

        # Sanity: localdate() should give London-date = 2025-06-16
        assert timezone.localdate() == datetime(2025, 6, 16).date()

        # Born on 2025-06-15 → age = 1 day at 00:30 BST on 2025-06-16
        chicken = ChickenFactory(date_of_birth=datetime(2025, 6, 15).date())

        assert chicken.age == 1, (
            f"Expected age=1 (local date is 2025-06-16), got {chicken.age}. "
            "If this fails with age=0, Chicken.age is likely using date.today() "
            "which returns the UTC date (2025-06-15) instead of the local date."
        )

    def test_age_at_gmt_midnight_matches_utc(self):
        """During GMT, local date == UTC date, so behaviour matches naive date.today()."""
        # Use a plain "today in London" DoB; age should be 0
        today_london = timezone.localdate()
        chicken = ChickenFactory(date_of_birth=today_london)
        assert chicken.age == 0

    def test_age_with_death_unaffected_by_timezone(self):
        """Dead chickens' ages are frozen and depend only on dob / dod."""
        chicken = ChickenFactory(
            date_of_birth=datetime(2024, 1, 1).date(),
            date_of_death=datetime(2024, 6, 1).date(),
        )
        expected = (datetime(2024, 6, 1).date() - datetime(2024, 1, 1).date()).days
        assert chicken.age == expected
