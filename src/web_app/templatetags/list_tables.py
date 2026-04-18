"""
Template tags for the list-style tables on the chicken and egg pages.

The main export is :func:`sort_header`, an inclusion tag that renders a
single ``<th>`` with a sort link and appropriate ``aria-sort`` /
``scope`` / mobile-visibility attributes. Previously each list template
hand-wrote the same tangled if/elif/else block, and the two versions
had drifted (different label formats, one had ``scope="col"`` and the
other didn't).
"""

from django import template

register = template.Library()


@register.inclusion_tag("web_app/partials/_sort_header.html")
def sort_header(
    col: str,
    label: str,
    current_sort: str,
    mobile: bool = True,
) -> dict:
    """Render a sortable table header cell.

    Args:
        col: query-string value that identifies this column. Ascending
            sort is ``?sort=col``; descending is ``?sort=-col``.
        label: human-readable column title.
        current_sort: the request's current ``?sort=…`` value (with or
            without the leading ``-``). Pass ``request.GET.get("sort", "")``
            or the view's ``sort`` context variable.
        mobile: whether to show this column below the md breakpoint.
            Pass ``False`` for columns that should be hidden on narrow
            screens via Bootstrap's ``d-none d-md-table-cell``.

    The corresponding partial renders:

    * ``scope="col"`` on every header,
    * ``aria-sort="ascending"`` / ``"descending"`` when this column
      matches the current sort,
    * direction-flipping href,
    * an accessible ``aria-label`` describing the current state, and
    * a visually-hidden-from-screen-readers arrow (``▲`` / ``▼``).
    """
    if current_sort == col:
        direction = "ascending"
        next_href = f"?sort=-{col}"
        arrow = "▲"
    elif current_sort == f"-{col}":
        direction = "descending"
        next_href = f"?sort={col}"
        arrow = "▼"
    else:
        direction = None
        next_href = f"?sort={col}"
        arrow = ""

    return {
        "col": col,
        "label": label,
        "mobile": mobile,
        "direction": direction,
        "next_href": next_href,
        "arrow": arrow,
    }
