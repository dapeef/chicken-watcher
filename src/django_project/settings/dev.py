# ruff: noqa: F405

from .base import *  # noqa: F403

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Dev fallback: if DJANGO_SECRET_KEY is not set in the environment, use a
# predictable, insecure value. This keeps `manage.py runserver` and the test
# suite working without any env setup.
#
# prod.py does NOT fall back like this — it requires a real secret or fails
# fast at startup.
if not SECRET_KEY:
    SECRET_KEY = "django-insecure-dev-key-do-not-use-in-production"

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
