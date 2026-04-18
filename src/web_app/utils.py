"""
Backwards-compatibility shim.

The analytics helpers that used to live here have moved to
``web_app.analytics``. This module re-exports the most-used names so any
external callers / third-party code continue to work. New code should
import from ``web_app.analytics`` directly.
"""

from .analytics import (  # noqa: F401  (re-export)
    CENTER,
    LEFT,
    RIGHT,
    rolling_average,
)
