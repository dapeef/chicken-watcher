"""Tests for the sort_header inclusion tag."""

from django.template import Context, Template


def _render(col: str, label: str, current_sort: str, mobile: bool = True) -> str:
    tmpl = Template("{% load list_tables %}{% sort_header col label current_sort mobile %}")
    return tmpl.render(
        Context(
            {
                "col": col,
                "label": label,
                "current_sort": current_sort,
                "mobile": mobile,
            }
        )
    )


class TestSortHeader:
    def test_unsorted_column_has_no_aria_sort(self):
        html = _render("name", "Name", current_sort="-laid_at")
        assert "aria-sort" not in html
        # Unsorted click goes to ascending
        assert 'href="?sort=name"' in html
        # Accessible label describes the action
        assert 'aria-label="Sort by Name"' in html
        # No visible arrow
        assert "▲" not in html
        assert "▼" not in html

    def test_ascending_column_has_aria_sort_and_up_arrow(self):
        html = _render("name", "Name", current_sort="name")
        assert 'aria-sort="ascending"' in html
        assert "▲" in html
        # Clicking flips to descending
        assert 'href="?sort=-name"' in html

    def test_descending_column_has_aria_sort_and_down_arrow(self):
        html = _render("name", "Name", current_sort="-name")
        assert 'aria-sort="descending"' in html
        assert "▼" in html
        # Clicking flips to ascending
        assert 'href="?sort=name"' in html

    def test_scope_col_always_present(self):
        for sort in ("", "name", "-name", "-laid_at"):
            html = _render("name", "Name", current_sort=sort)
            assert 'scope="col"' in html

    def test_mobile_false_hides_below_md(self):
        html = _render("name", "Name", current_sort="", mobile=False)
        assert "d-none d-md-table-cell" in html

    def test_mobile_true_does_not_add_hide_classes(self):
        html = _render("name", "Name", current_sort="", mobile=True)
        assert "d-none d-md-table-cell" not in html

    def test_arrow_is_hidden_from_screen_readers(self):
        """The ▲ / ▼ glyphs don't convey information beyond what
        aria-sort already provides, so they're wrapped in a span with
        aria-hidden to avoid duplicate announcements."""
        html = _render("name", "Name", current_sort="name")
        assert 'aria-hidden="true"' in html

    def test_label_is_human_readable_not_column_key(self):
        """The rendered cell shows the ``label`` argument, not the
        ``col`` key (which is a query-string identifier)."""
        html = _render("date_of_birth", "Hatched on", current_sort="")
        assert "Hatched on" in html
        # The snake-case col key shouldn't appear as user-visible text
        # (it's fine inside href= / aria-label).
        assert ">date_of_birth<" not in html
