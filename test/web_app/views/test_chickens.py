import json
from datetime import UTC, date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
    NestingBoxPresencePeriodFactory,
)


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

    def test_row_has_real_link_not_onclick_handler(self, client):
        """Regression: rows previously used <tr onclick='location.href=...'>
        which was not keyboard-accessible and broke open-in-new-tab.
        A real <a href> on the chicken name is both accessible and
        middle-clickable."""
        hen = ChickenFactory(name="Henrietta")
        response = client.get(self.url)
        content = response.content.decode()

        # No inline onclick handler anywhere in the list
        assert "onclick=" not in content, (
            "Found inline onclick — the row-click pattern is not "
            "keyboard accessible. Use a real <a href> on the name cell."
        )
        # The chicken name should be rendered inside an <a> pointing at
        # its detail URL.
        expected_href = reverse("chicken_detail", kwargs={"pk": hen.pk})
        assert f'href="{expected_href}"' in content
        assert "Henrietta" in content

    def test_whole_row_is_clickable_via_stretched_link(self, client):
        """The entire table row should be clickable, not just the chicken
        name. Bootstrap's stretched-link expands a positioned <a> to cover
        its nearest positioned ancestor.

        Requirements:
        - The <tr> must have ``position: relative`` (or Bootstrap's
          ``position-relative`` class) so stretched-link has a containing
          block to fill.
        - The <a> must carry the ``stretched-link`` class.
        - The ``href`` must point to the chicken detail URL.

        This test was added after a regression where the Wave 4 onclick
        removal left only the name cell clickable.
        """
        hen = ChickenFactory(name="Henrietta")
        response = client.get(self.url)
        content = response.content.decode()

        expected_href = reverse("chicken_detail", kwargs={"pk": hen.pk})

        # The link must have stretched-link so its click area fills the row.
        assert "stretched-link" in content, (
            "stretched-link class not found — clicking outside the name "
            "cell will not navigate to the chicken detail page."
        )
        # The <tr> containing the link must be a positioning context.
        assert "position: relative" in content or "position-relative" in content, (
            "The <tr> needs position:relative (or the Bootstrap "
            "position-relative class) for stretched-link to work."
        )
        # The href is still present and correct.
        assert f'href="{expected_href}"' in content

    def test_table_has_scope_col_on_headers(self, client):
        """Accessibility: <th>s in a table header should have
        ``scope='col'`` so screen readers announce the header for each
        data cell. Without scope, the association is guessed."""
        ChickenFactory()
        response = client.get(self.url)
        content = response.content.decode()
        # Pick any of the headers — all should carry scope="col".
        assert 'scope="col"' in content

    def test_sortable_headers_have_aria_sort(self, client):
        """When a column is currently sorted, the corresponding <th>
        should advertise ``aria-sort='ascending'`` or
        ``aria-sort='descending'`` so assistive tech knows the current
        sort state."""
        ChickenFactory()
        response = client.get(self.url + "?sort=name")
        content = response.content.decode()
        assert 'aria-sort="ascending"' in content

        response = client.get(self.url + "?sort=-name")
        content = response.content.decode()
        assert 'aria-sort="descending"' in content

    def test_all_expected_headers_present(self, client):
        response = client.get(self.url)
        header_keys = [col for col, _, _mobile in response.context["headers"]]
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
        """The age_duration annotation gives a timedelta from dob to today.

        We can't pin the DB's NOW() (used in Cast(Now(), DateField())),
        so instead of asserting an exact number of days, we check that
        the annotation is within ±1 day of the independently-computed
        age. A ±1 tolerance is needed because the DB may use UTC date
        while the test computes using local date, and they can differ by
        1 day near midnight.
        """
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=100)
        chicken = ChickenFactory(date_of_birth=dob, date_of_death=None)
        response = client.get(self.url)
        hen = next(c for c in response.context["object_list"] if c.pk == chicken.pk)
        # Allow ±1 day tolerance for DB/local-date boundary.
        assert abs(hen.age_duration.days - 100) <= 1

    def test_age_duration_capped_at_date_of_death(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        dob = today - timedelta(days=200)
        dod = today - timedelta(days=50)
        chicken = ChickenFactory(date_of_birth=dob, date_of_death=dod)
        response = client.get(self.url)
        hen = next(c for c in response.context["object_list"] if c.pk == chicken.pk)
        # Both dob and dod are fixed past dates — no time-of-day sensitivity.
        assert hen.age_duration.days == 150

    def test_age_rendered_as_ymd_in_html(self, client):
        from django.utils import timezone

        today = timezone.localdate()
        # Choose a DoB that gives the same formatted output regardless
        # of whether DB uses UTC or local date (both > 40 days ago).
        # 100 days = 3m 9d or similar — avoid "exactly 42d" which is
        # sensitive to the UTC↔BST day boundary.
        dob = today - timedelta(days=100)
        ChickenFactory(date_of_birth=dob, date_of_death=None)
        response = client.get(self.url)
        # The formatted age should contain a months component.
        assert b"m " in response.content and b"d" in response.content

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
        EggFactory.create_batch(5, chicken=chicken, laid_at=timezone.now() - timedelta(days=1))

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

    def test_chicken_timeline_data_excludes_other_chickens(self, client, mocker):
        """Periods for other chickens must not appear. Pinned to midday
        so night_periods don't overlap the ±1h query window."""
        from datetime import datetime

        fixed_noon = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
        mocker.patch("django.utils.timezone.now", return_value=fixed_noon)

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
