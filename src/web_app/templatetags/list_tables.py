"""
Template tags for list-style tables and dashboard panels.

* :func:`sort_header` — renders a single sortable ``<th>`` with correct
  ``aria-sort``, ``scope``, and keyboard-accessible link. Previously
  each list template hand-wrote the same tangled if/elif/else block,
  and the two versions had drifted (different label formats, one had
  ``scope="col"`` and the other didn't).

* :func:`htmx_poll_panel` — wraps a partial in the Bootstrap column
  classes + HTMX polling attributes that every live dashboard panel
  needs. Consolidates five near-identical ``<div>`` blocks on the
  dashboard page.
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


@register.inclusion_tag("web_app/partials/_htmx_poll_panel.html", takes_context=True)
def htmx_poll_panel(
    context,
    partial: str,
    url: str,
    columns: str = "col-12",
    interval_seconds: int = 5,
) -> dict:
    """Wrap a partial in an HTMX-polling Bootstrap column.

    Args:
        partial: template path of the partial to render on first load
            (e.g. ``"web_app/partials/_eggs_today.html"``).
        url: URL the panel polls for fresh HTML.
        columns: Bootstrap grid classes for the containing <div>.
            Defaults to full width (``"col-12"``).
        interval_seconds: HTMX polling interval. Matches the
            ``every Ns`` syntax of ``hx-trigger``.

    The rendered partial is included in the initial render too, so
    there's no flash of empty content while the first poll returns.
    ``takes_context=True`` forwards the outer template's context to
    the inclusion template so the included partial can read the usual
    dashboard context variables (``eggs_today``, ``latest_presence``
    etc.) exactly as if it had been included directly.
    """
    # Flatten the outer context onto the returned dict so the
    # inclusion template inherits every variable the caller had.
    merged = context.flatten()
    merged.update(
        {
            "partial": partial,
            "url": url,
            "columns": columns,
            "interval_seconds": interval_seconds,
        }
    )
    return merged
