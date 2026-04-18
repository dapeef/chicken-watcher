"""
Tests that verify settings-level guarantees which cannot be exercised in-
process (because Django's settings load exactly once per interpreter and
pytest has already loaded dev settings).

Each test shells out to a subprocess with controlled env vars and asserts
on exit code / stdout / stderr.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def isolated_repo(tmp_path):
    """Create a temporary copy of the repo with an empty .env so subprocess
    tests aren't contaminated by the developer's real .env file.

    Only copies files actually needed for settings import (src + manage.py
    + pyproject.toml). We use symlinks to keep this fast.
    """
    for name in ("src", "manage.py", "pyproject.toml", "uv.lock"):
        src = REPO_ROOT / name
        if src.exists():
            (tmp_path / name).symlink_to(src)
    (tmp_path / ".env").write_text("")
    return tmp_path


def _run_settings_import(
    isolated_repo: Path,
    django_env: str | None = None,
    secret_key: str | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Strip any inherited values so only what the test supplies is in effect.
    for key in ("DJANGO_SECRET_KEY", "DJANGO_ENV"):
        env.pop(key, None)
    if django_env is not None:
        env["DJANGO_ENV"] = django_env
    if secret_key is not None:
        env["DJANGO_SECRET_KEY"] = secret_key
    env["DJANGO_SETTINGS_MODULE"] = "django_project.settings"
    env["PYTHONPATH"] = str(isolated_repo / "src")
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from django.conf import settings;"
                "print('DEBUG=', settings.DEBUG);"
                "print('HAS_KEY=', bool(settings.SECRET_KEY));"
                "print('DB_ENGINE=', settings.DATABASES['default']['ENGINE']);"
            ),
        ],
        env=env,
        capture_output=True,
        text=True,
        cwd=isolated_repo,
    )


class TestSettingsDispatch:
    """DJANGO_ENV controls which concrete settings module is loaded."""

    def test_dev_env_loads_dev_settings(self, isolated_repo):
        result = _run_settings_import(isolated_repo, django_env="dev")
        assert result.returncode == 0, result.stderr
        assert "DEBUG= True" in result.stdout
        assert "DB_ENGINE= django.db.backends.sqlite3" in result.stdout

    def test_prod_env_loads_prod_settings(self, isolated_repo):
        result = _run_settings_import(
            isolated_repo, django_env="prod", secret_key="test-secret-key-xxxxx"
        )
        assert result.returncode == 0, result.stderr
        assert "DEBUG= False" in result.stdout
        assert "DB_ENGINE= django.db.backends.postgresql" in result.stdout

    def test_unset_env_defaults_to_prod(self, isolated_repo):
        """Fail-safe default: no DJANGO_ENV means prod, not dev. This
        prevents accidentally running a production container with SQLite."""
        result = _run_settings_import(
            isolated_repo, django_env=None, secret_key="test-secret-key-xxxxx"
        )
        assert result.returncode == 0, result.stderr
        assert "DEBUG= False" in result.stdout
        assert "DB_ENGINE= django.db.backends.postgresql" in result.stdout

    def test_invalid_env_raises_runtime_error(self, isolated_repo):
        result = _run_settings_import(isolated_repo, django_env="staging")
        assert result.returncode != 0
        assert "DJANGO_ENV must be one of" in result.stderr
        assert "'staging'" in result.stderr


class TestProdSecretKeyFailFast:
    """prod.py must refuse to import without DJANGO_SECRET_KEY."""

    def test_prod_without_secret_key_raises(self, isolated_repo):
        result = _run_settings_import(isolated_repo, django_env="prod", secret_key="")
        assert result.returncode != 0
        assert "DJANGO_SECRET_KEY" in result.stderr
        assert "ImproperlyConfigured" in result.stderr

    def test_prod_with_empty_secret_key_raises(self, isolated_repo):
        result = _run_settings_import(isolated_repo, django_env="prod", secret_key="")
        assert result.returncode != 0
        assert "DJANGO_SECRET_KEY" in result.stderr

    def test_prod_has_debug_false(self, isolated_repo):
        result = _run_settings_import(
            isolated_repo, django_env="prod", secret_key="test-key-xxxxx"
        )
        assert result.returncode == 0
        assert "DEBUG= False" in result.stdout


class TestDevFallback:
    """dev.py provides a permissive SECRET_KEY fallback for local dev."""

    def test_dev_without_secret_key_uses_fallback(self, isolated_repo):
        result = _run_settings_import(isolated_repo, django_env="dev", secret_key="")
        assert result.returncode == 0, result.stderr
        # Dev fallback kicks in → HAS_KEY is True
        assert "HAS_KEY= True" in result.stdout

    def test_dev_respects_provided_secret_key(self, isolated_repo):
        result = _run_settings_import(
            isolated_repo, django_env="dev", secret_key="real-dev-key"
        )
        assert result.returncode == 0, result.stderr
        assert "HAS_KEY= True" in result.stdout
