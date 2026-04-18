"""
Tests for the logging config in django_project.settings.base.

Like test_settings.py, these use subprocesses because LOGGING is evaluated
at settings-import time.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def isolated_repo(tmp_path):
    for name in ("src", "manage.py", "pyproject.toml", "uv.lock"):
        src = REPO_ROOT / name
        if src.exists():
            (tmp_path / name).symlink_to(src)
    (tmp_path / ".env").write_text("")
    return tmp_path


def _probe_logging_config(
    isolated_repo: Path,
    env_overrides: dict[str, str] | None = None,
) -> dict:
    """Import settings in a subprocess and return a dict summarising the
    computed LOGGING config."""
    env = os.environ.copy()
    for key in (
        "DJANGO_SECRET_KEY",
        "DJANGO_ENV",
        "LOG_LEVEL",
        "LOG_DIR",
        "LOG_FILENAME",
        "LOG_FILE_BYTES",
        "LOG_FILE_BACKUP_COUNT",
        "DJANGO_DB_LOG_LEVEL",
    ):
        env.pop(key, None)
    env["DJANGO_ENV"] = "dev"
    env["DJANGO_SETTINGS_MODULE"] = "django_project.settings"
    env["PYTHONPATH"] = str(isolated_repo / "src")
    if env_overrides:
        env.update(env_overrides)

    script = """
import json
from django.conf import settings
out = {
    "root_level": settings.LOGGING["root"]["level"],
    "root_handlers": settings.LOGGING["root"]["handlers"],
    "handler_names": sorted(settings.LOGGING["handlers"].keys()),
    "logs_dir": settings.LOGS_DIR,
    "db_backend_level": settings.LOGGING["loggers"]["django.db.backends"]["level"],
}
print("CONFIG=" + json.dumps(out))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        cwd=isolated_repo,
    )
    assert result.returncode == 0, result.stderr
    import json

    for line in result.stdout.splitlines():
        if line.startswith("CONFIG="):
            return json.loads(line.removeprefix("CONFIG="))
    raise AssertionError(f"No CONFIG= line in output: {result.stdout!r}")


class TestLoggingDefaults:
    def test_default_level_is_info(self, isolated_repo):
        config = _probe_logging_config(isolated_repo)
        assert config["root_level"] == "INFO"

    def test_default_has_console_and_file(self, isolated_repo):
        config = _probe_logging_config(isolated_repo)
        assert "console" in config["root_handlers"]
        assert "file" in config["root_handlers"]

    def test_django_db_logger_pinned_to_info(self, isolated_repo):
        """Even when LOG_LEVEL=DEBUG, SQL echo stays quiet unless the user
        explicitly opts in."""
        config = _probe_logging_config(
            isolated_repo, env_overrides={"LOG_LEVEL": "DEBUG"}
        )
        assert config["root_level"] == "DEBUG"
        assert config["db_backend_level"] == "INFO"

    def test_db_log_level_can_be_overridden(self, isolated_repo):
        config = _probe_logging_config(
            isolated_repo, env_overrides={"DJANGO_DB_LOG_LEVEL": "DEBUG"}
        )
        assert config["db_backend_level"] == "DEBUG"


class TestLoggingEnvOverrides:
    def test_log_level_env_overrides_root_level(self, isolated_repo):
        config = _probe_logging_config(
            isolated_repo, env_overrides={"LOG_LEVEL": "WARNING"}
        )
        assert config["root_level"] == "WARNING"

    def test_log_dir_env_overrides_default(self, isolated_repo, tmp_path):
        custom_dir = tmp_path / "custom_logs"
        config = _probe_logging_config(
            isolated_repo, env_overrides={"LOG_DIR": str(custom_dir)}
        )
        assert config["logs_dir"] == str(custom_dir)
        assert custom_dir.exists(), "LOG_DIR should be created on settings import"


class TestLoggingReadonlyFallback:
    def test_unwritable_log_dir_falls_back_to_console_only(
        self, isolated_repo, tmp_path
    ):
        """If LOG_DIR cannot be created or isn't writable, settings must not
        crash — instead, silently drop the file handler and keep console.
        This matters for tests / containers with read-only root FS."""
        # /proc is writable on Linux by root only — but a cleaner approach:
        # point LOG_DIR at a file (not a directory), which makes makedirs
        # fail with NotADirectoryError.
        not_a_dir = tmp_path / "iam_a_file"
        not_a_dir.write_text("nope")

        config = _probe_logging_config(
            isolated_repo, env_overrides={"LOG_DIR": str(not_a_dir)}
        )
        # Only the console handler should be configured.
        assert config["root_handlers"] == ["console"]
        assert "file" not in config["handler_names"]
