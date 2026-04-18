"""
Settings dispatcher.

DJANGO_ENV must be one of: "prod", "dev".

Defaults to "prod" (fail-safe): if someone forgets to set DJANGO_ENV in a
production container they get the strict prod settings (requires a real
DJANGO_SECRET_KEY, uses Postgres) instead of silently falling back to
SQLite, which would silently drop data on container restart.

Tests and local development override this explicitly:
  - pytest uses `DJANGO_SETTINGS_MODULE=django_project.settings.dev`
    (see pyproject.toml).
  - `manage.py runserver` respects DJANGO_ENV=dev in a `.env` file.
"""

import os

_VALID_ENVS = {"prod", "dev"}
DJANGO_ENV = os.getenv("DJANGO_ENV", "prod")

if DJANGO_ENV not in _VALID_ENVS:
    raise RuntimeError(
        f"DJANGO_ENV must be one of {sorted(_VALID_ENVS)}, got {DJANGO_ENV!r}. "
        "Set DJANGO_ENV=dev for local development or DJANGO_ENV=prod in "
        "production."
    )

if DJANGO_ENV == "prod":
    from .prod import *  # noqa: F401,F403
else:
    from .dev import *  # noqa: F401,F403
