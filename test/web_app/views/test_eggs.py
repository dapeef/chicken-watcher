from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from web_app.models import Egg

from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
)


@pytest.mark.django_db
class TestEggViews:
    def test_egg_list_view(self, client):
        c1 = ChickenFactory(name="C1")
        c2 = ChickenFactory(name="C2")
        EggFactory(chicken=c1, laid_at=timezone.now() - timedelta(hours=1))
        EggFactory(chicken=c2, laid_at=timezone.now())

        url = reverse("egg_list")
        response = client.get(url)
        assert response.status_code == 200
        eggs = response.context["object_list"]
        assert len(eggs) == 2
        # Default sort is -laid_at
        assert eggs[0].chicken == c2
        assert eggs[1].chicken == c1

    def test_egg_create_view(self, client):
        chicken = ChickenFactory()
        box = NestingBoxFactory()
        url = reverse("egg_create")

        # GET
        response = client.get(url)
        assert response.status_code == 200

        # POST valid
        data = {
            "chicken": chicken.pk,
            "nesting_box": box.pk,
            "laid_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert Egg.objects.count() == 1

    def test_egg_delete_view_get_shows_confirmation(self, client):
        egg = EggFactory()
        url = reverse("egg_delete", args=[egg.pk])

        response = client.get(url)
        assert response.status_code == 200
        assert "Are you sure" in response.content.decode()

    def test_egg_delete_view_post_deletes_egg(self, client):
        egg = EggFactory()
        url = reverse("egg_delete", args=[egg.pk])

        response = client.post(url)
        assert response.status_code == 302
        assert Egg.objects.count() == 0

    def test_egg_delete_view_redirects_to_egg_list(self, client):
        egg = EggFactory()
        url = reverse("egg_delete", args=[egg.pk])

        response = client.post(url)
        assert response.url == reverse("egg_list")

    def test_egg_delete_view_nonexistent_egg_returns_404(self, client):
        url = reverse("egg_delete", args=[9999])

        response = client.get(url)
        assert response.status_code == 404

    def test_egg_create_view_messy_quality(self, client):
        url = reverse("egg_create")
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            "quality": "messy",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert Egg.objects.filter(quality="messy").count() == 1

    def test_egg_create_view_quality_defaults_to_saleable(self, client):
        url = reverse("egg_create")
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
        }
        response = client.post(url, data)
        assert response.status_code == 302
        assert Egg.objects.filter(quality="saleable").count() == 1

    def test_egg_list_shows_quality_column(self, client):
        EggFactory(quality="messy")
        EggFactory(quality="saleable")
        EggFactory(quality="edible")
        url = reverse("egg_list")
        response = client.get(url)
        content = response.content.decode()
        assert "Quality" in content
        assert "Messy" in content
        assert "Saleable" in content
        assert "Edible" in content

    def test_egg_list_shows_edit_button(self, client):
        egg = EggFactory()
        response = client.get(reverse("egg_list"))
        content = response.content.decode()
        assert f"/eggs/{egg.pk}/edit/" in content
        assert "Edit" in content

    # ── edit view ─────────────────────────────────────────────────────────────

    def test_egg_edit_view_get(self, client):
        egg = EggFactory()
        response = client.get(reverse("egg_edit", args=[egg.pk]))
        assert response.status_code == 200
        assert "Edit egg" in response.content.decode()

    def test_egg_edit_view_nonexistent_returns_404(self, client):
        response = client.get(reverse("egg_edit", args=[9999]))
        assert response.status_code == 404

    def test_egg_edit_view_updates_quality(self, client):
        egg = EggFactory(quality="saleable")
        url = reverse("egg_edit", args=[egg.pk])
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": egg.laid_at.strftime("%Y-%m-%dT%H:%M"),
            "quality": "messy",
        }
        response = client.post(url, data)
        assert response.status_code == 302
        egg.refresh_from_db()
        assert egg.quality == "messy"

    def test_egg_edit_view_updates_chicken(self, client):
        chicken = ChickenFactory()
        egg = EggFactory(chicken=None)
        url = reverse("egg_edit", args=[egg.pk])
        data = {
            "chicken": chicken.pk,
            "nesting_box": "",
            "laid_at": egg.laid_at.strftime("%Y-%m-%dT%H:%M"),
            "quality": egg.quality,
        }
        response = client.post(url, data)
        assert response.status_code == 302
        egg.refresh_from_db()
        assert egg.chicken == chicken

    def test_egg_edit_view_redirects_to_egg_list(self, client):
        egg = EggFactory()
        url = reverse("egg_edit", args=[egg.pk])
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": egg.laid_at.strftime("%Y-%m-%dT%H:%M"),
            "quality": egg.quality,
        }
        response = client.post(url, data)
        assert response.url == reverse("egg_list")

    def test_egg_edit_view_cancel_link_present(self, client):
        egg = EggFactory()
        response = client.get(reverse("egg_edit", args=[egg.pk]))
        assert reverse("egg_list") in response.content.decode()

    def test_egg_edit_does_not_create_new_egg(self, client):
        egg = EggFactory()
        assert Egg.objects.count() == 1
        url = reverse("egg_edit", args=[egg.pk])
        data = {
            "chicken": "",
            "nesting_box": "",
            "laid_at": egg.laid_at.strftime("%Y-%m-%dT%H:%M"),
            "quality": "edible",
        }
        client.post(url, data)
        assert Egg.objects.count() == 1


@pytest.mark.django_db
class TestEggFormRendering:
    """Regression tests for the egg_form template. Previously the
    template hand-rendered every <input>/<select>, which drifted from
    the form definition and was hard to test. Now it uses
    _bs_field.html + Django's form rendering machinery."""

    def test_form_renders_bootstrap_classes(self, client):
        response = client.get(reverse("egg_create"))
        content = response.content.decode()
        # Bootstrap classes on the form controls
        assert "form-select" in content
        assert "form-control" in content
        assert "form-check-input" in content

    def test_quality_field_renders_as_radio_group(self, client):
        """Quality is a radio group (not a dropdown). All three
        options should render as <input type="radio">."""
        response = client.get(reverse("egg_create"))
        content = response.content.decode()
        assert content.count('type="radio"') == 3
        # Each quality label appears
        assert "Saleable" in content
        assert "Edible" in content
        assert "Messy" in content
        # Accessible radiogroup wrapper
        assert 'role="radiogroup"' in content

    def test_optional_fields_labelled_optional(self, client):
        response = client.get(reverse("egg_create"))
        content = response.content.decode()
        assert "(optional)" in content

    def test_empty_fk_choice_uses_unknown_label(self, client):
        """The chicken and nesting_box fields should render the
        empty option as '— Unknown —' rather than Django's default
        ``---------``."""
        response = client.get(reverse("egg_create"))
        content = response.content.decode()
        assert "— Unknown —" in content
        assert "---------" not in content

    def test_error_shows_when_post_with_invalid_data(self, client):
        """Posting obviously invalid data surfaces a field-level error
        rendered through the _bs_field partial."""
        response = client.post(
            reverse("egg_create"),
            {"laid_at": "not-a-datetime"},
        )
        assert response.status_code == 200
        # The form rerenders with an error
        content = response.content.decode()
        assert "text-danger" in content


@pytest.mark.django_db
class TestEggListPagination:
    """EggListView paginates by 50 rows. The ``?sort=`` param must
    survive across page links."""

    def test_list_is_paginated_at_51_eggs(self, client):
        for _ in range(51):
            EggFactory()
        response = client.get(reverse("egg_list"))
        assert response.status_code == 200
        assert response.context["is_paginated"] is True
        assert len(response.context["object_list"]) == 50

    def test_list_is_not_paginated_at_50_eggs(self, client):
        for _ in range(50):
            EggFactory()
        response = client.get(reverse("egg_list"))
        assert response.context["is_paginated"] is False

    def test_page_2_shows_remaining_eggs(self, client):
        for _ in range(51):
            EggFactory()
        response = client.get(reverse("egg_list") + "?page=2")
        assert response.status_code == 200
        assert len(response.context["object_list"]) == 1

    def test_sort_param_survives_across_pages(self, client):
        """The pagination partial should include ``?sort=…`` in every
        page link so clicking ``Next`` doesn't reset the sort."""
        for _ in range(60):
            EggFactory()
        response = client.get(reverse("egg_list") + "?sort=laid_at")
        content = response.content.decode()
        # The "Next" link should include both page=2 and sort=laid_at
        assert "page=2" in content
        assert "sort=laid_at" in content

    def test_querystring_without_page_excludes_page_param(self, client):
        """The helper context variable drops ``page`` so pagination
        links don't produce ``?page=3&page=2`` when you click Next
        from page 2."""
        for _ in range(60):
            EggFactory()
        response = client.get(reverse("egg_list") + "?sort=laid_at&page=2")
        qs = response.context["querystring_without_page"]
        assert "sort=laid_at" in qs
        assert "page=" not in qs


@pytest.mark.django_db
class TestEggListQueryCount:
    """Regression tests that the egg list view doesn't N+1 over
    chicken/nesting_box when rendering.

    Template iterates ``{{ egg.chicken.name }}`` and
    ``{{ egg.nesting_box.name }}`` for every row. Without
    ``select_related``, a 200-egg page produces 401 queries (1 for the
    list + 200 for chickens + 200 for boxes). With it, 1.
    """

    def test_egg_list_is_constant_query_count(self, client, django_assert_max_num_queries):
        # Create a mix of eggs so chicken and box FK lookups both fire.
        for _ in range(10):
            EggFactory()

        # Budget: the list query itself + session/other middleware queries.
        # We assert on a small, generous ceiling rather than an exact number
        # so unrelated middleware changes don't break this regression test.
        with django_assert_max_num_queries(10):
            response = client.get(reverse("egg_list"))
            assert response.status_code == 200
            # Force the template to render all rows (Django querysets are lazy)
            list(response.context["object_list"])
            # Access FK fields to trigger any lazy loads
            for egg in response.context["object_list"]:
                _ = egg.chicken and egg.chicken.name
                _ = egg.nesting_box and egg.nesting_box.name

    def test_egg_list_query_count_does_not_grow_with_egg_count(
        self, client, django_assert_max_num_queries
    ):
        """Whether 1 egg or 50, query count should be the same."""
        for _ in range(50):
            EggFactory()

        with django_assert_max_num_queries(10):
            response = client.get(reverse("egg_list"))
            assert response.status_code == 200
            for egg in response.context["object_list"]:
                _ = egg.chicken and egg.chicken.name
                _ = egg.nesting_box and egg.nesting_box.name
