from datetime import timedelta

from django import template

register = template.Library()


def _years_months_days(total_days: int) -> tuple[int, int, int]:
    """
    Convert a number of days into (years, months, days).

    Uses 365-day years and 30-day months for the remainder, which is accurate
    enough for displaying ages and avoids calendar-arithmetic edge cases.
    """
    years, remainder = divmod(total_days, 365)
    months, days = divmod(remainder, 30)
    return years, months, days


@register.filter
def duration_ymd(value) -> str:
    """
    Render a timedelta (or integer day count) as a human-readable age string
    in the form "2y 3m 5d", omitting leading zero components.

    Examples:
        timedelta(days=400)  -> "1y 1m 5d"
        timedelta(days=35)   -> "1m 5d"
        timedelta(days=5)    -> "5d"
        timedelta(days=0)    -> "0d"
        None / non-numeric   -> ""
    """
    if value is None:
        return ""
    try:
        total_days = value.days if isinstance(value, timedelta) else int(value)
    except (TypeError, ValueError):
        return ""

    if total_days < 0:
        return ""

    years, months, days = _years_months_days(total_days)

    parts = []
    if years:
        parts.append(f"{years}y")
    if months or years:  # show months once we have at least a year to display
        parts.append(f"{months}m")
    parts.append(f"{days}d")

    return " ".join(parts)
