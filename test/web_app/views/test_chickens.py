import pytest
import json
from datetime import date, timedelta, datetime, timezone as dt_timezone
from django.urls import reverse
from django.utils import timezone
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
    NestingBoxPresencePeriodFactory,
)
from web_app.views.chickens import (
    nesting_time_of_day,
    egg_time_of_day_kde,
    BUCKET_MINUTES,
    BUCKETS_PER_DAY,
)


def make_period(started_at, ended_at):
    """Build an unsaved NestingBoxPresencePeriod-like object for unit tests."""
    p = NestingBoxPresencePeriodFactory.build(
        started_at=started_at,
        ended_at=ended_at,
    )
    return p


def utc(hour, minute=0, day=1):
    """Return a UTC-aware datetime on an arbitrary fixed date."""
    return datetime(2024, 1, day, hour, minute, tzinfo=dt_timezone.utc)


class TestNestingTimeOfDay:
    def test_empty_periods(self):
        counts = nesting_time_of_day([])
        assert len(counts) == BUCKETS_PER_DAY
        assert all(c == 0 for c in counts)

    def test_single_period_within_one_bucket(self):
        # 10:02 – 10:07 falls entirely inside bucket 10:00–10:10 (index 60)
        period = make_period(utc(10, 2), utc(10, 7))
        counts = nesting_time_of_day([period])
        bucket = (10 * 60) // BUCKET_MINUTES  # index 60
        assert counts[bucket] == 1
        assert sum(counts) == 1

    def test_period_spanning_two_buckets(self):
        # 10:05 – 10:15 spans buckets 10:00 (index 60) and 10:10 (index 61)
        period = make_period(utc(10, 5), utc(10, 15))
        counts = nesting_time_of_day([period])
        assert counts[60] == 1
        assert counts[61] == 1
        assert sum(counts) == 2

    def test_same_chicken_same_bucket_two_different_days(self):
        # Two periods on different days, both in the 10:00 bucket → count = 2
        p1 = make_period(utc(10, 2, day=1), utc(10, 7, day=1))
        p2 = make_period(utc(10, 2, day=2), utc(10, 7, day=2))
        counts = nesting_time_of_day([p1, p2])
        bucket = (10 * 60) // BUCKET_MINUTES
        assert counts[bucket] == 2

    def test_same_day_two_periods_same_bucket_counted_once(self):
        # Two periods on the same day, both in the 10:00 bucket → count = 1
        p1 = make_period(utc(10, 0, day=1), utc(10, 5, day=1))
        p2 = make_period(utc(10, 5, day=1), utc(10, 9, day=1))
        counts = nesting_time_of_day([p1, p2])
        bucket = (10 * 60) // BUCKET_MINUTES
        assert counts[bucket] == 1

    def test_period_spanning_midnight(self):
        # 23:55 day 1 to 00:05 day 2 — spans bucket 23:50 (index 143) and 00:00 (index 0)
        p = make_period(utc(23, 55, day=1), utc(0, 5, day=2))
        counts = nesting_time_of_day([p])
        assert counts[0] == 1  # 00:00 bucket, hit on day 2
        assert counts[143] == 1  # 23:50 bucket, hit on day 1


@pytest.mark.django_db
class TestChickenListView:
    url = reverse("chicken_list")

    # --- basic rendering ---

    def test_empty_list(self, client):
        response = client.get(self.url)
        assert response.status_code == 200
        assert len(response.context["object_list"]) == 0

    def test_chickens_appear_in_list(self, client):
        ChickenFactory(name="Bertha")
        ChickenFactory(name="Alice")
        response = client.get(self.url)
        assert response.status_code == 200
        names = {c.name for c in response.context["object_list"]}
        assert names == {"Bertha", "Alice"}

    def test_all_expected_headers_present(self, client):
        response = client.get(self.url)
        header_keys = [col for col, _ in response.context["headers"]]
        assert "name" in header_keys
        assert "age_duration" in header_keys
        assert "tag__number" in header_keys
        assert "eggs_total" in header_keys
        assert "last_egg" in header_keys
        assert "date_of_birth" in header_keys
        assert "date_of_death" in header_keys

    def test_html_contains_age_and_tag_columns(self, client):
        response = client.get(self.url)
        assert b"Age" in response.content
        assert b"Tag number" in response.content

    # --- sorting ---

    def test_default_sort_is_by_name_ascending(self, client):
        ChickenFactory(name="Zelda")
        ChickenFactory(name="Alice")
        response = client.get(self.url)
        names = [c.name for c in response.context["object_list"]]
        assert names == sorted(names)

    def test_sort_by_name_descending(self, client):
        ChickenFactory(name="Bertha")
        ChickenFactory(name="Alice")
        response = client.get(self.url + "?sort=-name")
        names = [c.name for c in response.context["object_list"]]
        assert names == ["Bertha", "Alice"]

    def test_sort_context_reflects_query_param(self, client):
        response = client.get(self.url + "?sort=age_duration")
        assert response.context["sort"] == "age_duration"

    def test_sort_by_age_duration_ascending(self, client):
        today = date.today()
        young = ChickenFactory(date_of_birth=today - timedelta(days=10))
        old = ChickenFactory(date_of_birth=today - timedelta(days=200))
        response = client.get(self.url + "?sort=age_duration")
        ids = [c.pk for c in response.context["object_list"]]
        assert ids == [young.pk, old.pk]

    def test_sort_by_eggs_total_descending(self, client):
        few = ChickenFactory()
        many = ChickenFactory()
        EggFactory.create_batch(5, chicken=many)
        EggFactory.create_batch(1, chicken=few)
        response = client.get(self.url + "?sort=-eggs_total")
        ids = [c.pk for c in response.context["object_list"]]
        assert ids[0] == many.pk

    # --- age_days annotation ---

    def test_age_duration_for_living_chicken(self, client):
        today = date.today()
        dob = today - timedelta(days=100)
        chicken = ChickenFactory(date_of_birth=dob, date_of_death=None)
        response = client.get(self.url)
        hen = next(c for c in response.context["object_list"] if c.pk == chicken.pk)
        assert hen.age_duration.days == 100

    def test_age_duration_capped_at_date_of_death(self, client):
        today = date.today()
        dob = today - timedelta(days=200)
        dod = today - timedelta(days=50)
        chicken = ChickenFactory(date_of_birth=dob, date_of_death=dod)
        response = client.get(self.url)
        hen = next(c for c in response.context["object_list"] if c.pk == chicken.pk)
        assert hen.age_duration.days == 150

    def test_age_rendered_as_ymd_in_html(self, client):
        today = date.today()
        # 42 days = 1m 12d
        ChickenFactory(date_of_birth=today - timedelta(days=42), date_of_death=None)
        response = client.get(self.url)
        assert b"1m 12d" in response.content

    # --- tag number ---

    def test_tag_number_shown_when_tag_assigned(self, client):
        from ..factories import TagFactory

        tag = TagFactory(number=99)
        ChickenFactory(tag=tag)
        response = client.get(self.url)
        assert b"99" in response.content

    def test_tag_number_dash_when_no_tag(self, client):
        ChickenFactory(tag=None)
        response = client.get(self.url)
        assert "—".encode() in response.content

    def test_tag_number_value_on_queryset(self, client):
        from ..factories import TagFactory

        tag = TagFactory(number=7)
        chicken = ChickenFactory(tag=tag)
        response = client.get(self.url)
        hen = next(c for c in response.context["object_list"] if c.pk == chicken.pk)
        assert hen.tag.number == 7

    def test_chicken_without_tag_has_none_tag(self, client):
        chicken = ChickenFactory(tag=None)
        response = client.get(self.url)
        hen = next(c for c in response.context["object_list"] if c.pk == chicken.pk)
        assert hen.tag is None


@pytest.mark.django_db
class TestChickenViews:
    def test_chicken_detail_view(self, client):
        chicken = ChickenFactory()
        EggFactory.create_batch(
            5, chicken=chicken, laid_at=timezone.now() - timedelta(days=1)
        )

        url = reverse("chicken_detail", kwargs={"pk": chicken.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert response.context["hen"] == chicken
        assert response.context["stats"]["total"] == 5

    def test_chicken_timeline_data_returns_periods_and_eggs(self, client):
        chicken = ChickenFactory()
        box = NestingBoxFactory(name="left")
        now = timezone.now()

        period = NestingBoxPresencePeriodFactory(
            chicken=chicken,
            nesting_box=box,
            started_at=now - timedelta(minutes=30),
            ended_at=now - timedelta(minutes=10),
        )
        egg = EggFactory(
            chicken=chicken,
            nesting_box=box,
            laid_at=now - timedelta(minutes=15),
        )

        start = (now - timedelta(hours=1)).isoformat()
        end = now.isoformat()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url, {"start": start, "end": end})

        assert response.status_code == 200
        data = json.loads(response.content)
        ids = {item["id"] for item in data}
        assert f"period_{period.id}" in ids
        assert f"egg_{egg.id}" in ids

    def test_chicken_timeline_data_excludes_other_chickens(self, client):
        chicken = ChickenFactory()
        other = ChickenFactory()
        box = NestingBoxFactory(name="left")
        now = timezone.now()

        NestingBoxPresencePeriodFactory(
            chicken=other,
            nesting_box=box,
            started_at=now - timedelta(minutes=30),
            ended_at=now - timedelta(minutes=10),
        )

        start = (now - timedelta(hours=1)).isoformat()
        end = now.isoformat()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url, {"start": start, "end": end})

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data == []

    def test_chicken_timeline_data_missing_params_returns_empty(self, client):
        chicken = ChickenFactory()
        url = reverse("chicken_timeline_data", kwargs={"pk": chicken.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert json.loads(response.content) == []

    def test_chicken_timeline_data_invalid_chicken_returns_404(self, client):
        url = reverse("chicken_timeline_data", kwargs={"pk": 99999})
        response = client.get(url)
        assert response.status_code == 404


def make_egg(laid_at):
    """Build an unsaved Egg-like object for unit tests."""
    return EggFactory.build(laid_at=laid_at)


class TestEggTimeOfDayKde:
    def test_empty_returns_all_zeros(self):
        result = egg_time_of_day_kde([])
        assert len(result) == BUCKETS_PER_DAY
        assert all(v == 0.0 for v in result)

    def test_result_length(self):
        egg = make_egg(utc(10, 0))
        result = egg_time_of_day_kde([egg])
        assert len(result) == BUCKETS_PER_DAY

    def test_single_egg_peak_near_its_time(self):
        # Egg at 10:00 UTC — the peak bucket should be at or near 10:00
        egg = make_egg(utc(10, 0))
        result = egg_time_of_day_kde([egg])
        peak_bucket = result.index(max(result))
        peak_minutes = peak_bucket * BUCKET_MINUTES
        # Peak should be within one bucket of 10:00 (600 minutes)
        assert abs(peak_minutes - 600) <= BUCKET_MINUTES

    def test_all_values_non_negative(self):
        eggs = [make_egg(utc(h)) for h in range(0, 24, 3)]
        result = egg_time_of_day_kde(eggs)
        assert all(v >= 0 for v in result)

    def test_integrates_to_approximately_one(self):
        # The KDE produces density in units of probability per minute.
        # Summing all buckets and multiplying by BUCKET_MINUTES gives total
        # probability mass, which should be ≈ 1.
        eggs = [make_egg(utc(h)) for h in range(0, 24, 2)]
        result = egg_time_of_day_kde(eggs)
        total = sum(result) * BUCKET_MINUTES
        # Allow generous tolerance because we're on a discrete grid
        assert abs(total - 1.0) < 0.05

    def test_midnight_egg_wraps_symmetrically(self):
        # An egg at midnight should produce a symmetric distribution
        # with its peak at bucket 0 (00:00)
        egg = make_egg(utc(0, 0))
        result = egg_time_of_day_kde([egg])
        assert result[0] == max(result)
        # And the distribution should be symmetric: bucket 1 ≈ bucket 143
        assert abs(result[1] - result[143]) < 1e-6

    def test_larger_bandwidth_gives_broader_peak(self):
        egg = make_egg(utc(10, 0))
        narrow = egg_time_of_day_kde([egg], bandwidth=10)
        wide = egg_time_of_day_kde([egg], bandwidth=60)
        # Wider bandwidth → smaller peak value (mass spread over more buckets)
        assert max(wide) < max(narrow)
        # Peak location should still be at the same bucket
        assert narrow.index(max(narrow)) == wide.index(max(wide))

    def test_bandwidth_zero_raises_or_produces_spike(self):
        # Extremely small bandwidth should produce a very sharp, tall peak
        egg = make_egg(utc(10, 0))
        result = egg_time_of_day_kde([egg], bandwidth=1)
        peak_bucket = (10 * 60) // BUCKET_MINUTES
        # With bandwidth=1 the peak should dominate all other buckets
        assert result[peak_bucket] == max(result)
