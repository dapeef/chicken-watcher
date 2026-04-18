# ruff: noqa: F405

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

# SECURITY WARNING: never run production with DEBUG on. Among other things
# DEBUG=True leaks stack traces (including environment variables) on any
# 500 page, disables template caching, and changes middleware behaviour.
DEBUG = False

# SECURITY: the app is deployed on a trusted LAN, so HTTPS / session-cookie-
# secure / HSTS hardening is intentionally out of scope (see
# docs/tech-debt-review.md § "Outside-of-LAN Security Changes"). But the
# SECRET_KEY still matters — a missing or placeholder key means broken
# sessions and CSRF. Fail fast at import time rather than at the first
# request that happens to exercise sessions.
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY environment variable is required for prod settings. "
        'Generate one with: `python -c "import secrets; print(secrets.token_urlsafe(50))"`'
    )


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),  # name of the DB service
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}
