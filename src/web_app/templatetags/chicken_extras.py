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


@register.filter
def duration_hms(value) -> str:
    """
    Render a timedelta as a human-readable duration string, omitting leading
    zero components.  The smallest unit always shown is seconds.

    Seconds precision:
      - Under 1 minute: shown to 1 decimal place (e.g. "8.3 secs")
      - 1 minute or more: rounded to the nearest whole second

    Examples:
        timedelta(seconds=8.3)           -> "8.3 secs"
        timedelta(seconds=1)             -> "1.0 sec"
        timedelta(seconds=75)            -> "1 min, 15 secs"
        timedelta(seconds=3661)          -> "1 hr, 1 min, 1 sec"
        timedelta(hours=2, minutes=30)   -> "2 hrs, 30 mins, 0 secs"
        timedelta(0) / None / bad input  -> "0.0 secs"
    """
    if value is None:
        return "0.0 secs"
    try:
        total_seconds_f = (
            value.total_seconds() if isinstance(value, timedelta) else float(value)
        )
    except (TypeError, ValueError, AttributeError):
        return "0.0 secs"

    if total_seconds_f < 0:
        total_seconds_f = 0.0

    if total_seconds_f < 60:
        # Sub-minute: show one decimal place
        s = round(total_seconds_f, 1)
        label = "sec" if s == 1.0 else "secs"
        return f"{s} {label}"

    # 1 minute or more: work in whole seconds
    total_seconds = round(total_seconds_f)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours} {'hr' if hours == 1 else 'hrs'}")
    if minutes or hours:
        parts.append(f"{minutes} {'min' if minutes == 1 else 'mins'}")
    parts.append(f"{seconds} {'sec' if seconds == 1 else 'secs'}")

    return ", ".join(parts)
