# Chicken Watcher - Agent Instructions

## Project Overview

A Raspberry Pi-based IoT system that tracks which chicken lays which eggs in a chicken coop. It runs two main processes: a hardware polling daemon and a Django web application.

## Tech Stack

- **Language:** Python 3.13+
- **Package manager:** `uv`
- **Web framework:** Django 6.0 (ASGI via Uvicorn)
- **Database (prod):** PostgreSQL 16
- **Database (dev/test):** SQLite
- **Computer vision:** OpenCV (`opencv-python`)
- **Serial/RFID:** `pyserial`
- **GPIO / beam sensors:** `gpiozero` + `lgpio` (Linux ARM only)
- **Testing:** `pytest`, `pytest-django`, `pytest-mock`, `factory-boy`
- **Linting:** `ruff`
- **Containerisation:** Docker + Docker Compose

## Project Structure

```
src/
  django_project/        # Django project config (settings, urls, asgi/wsgi)
    settings/
      base.py            # Shared settings
      dev.py             # SQLite, DEBUG=True
      prod.py            # PostgreSQL
  hardware_agent/        # Hardware polling daemon
  web_app/               # Django web app (models, views, templates)
test/
  hardware_agent/        # Hardware agent tests
  web_app/               # Web app tests (includes factories.py)
scheduler/               # Cron job definitions
```

## Running Tests

Tests always run against SQLite (dev settings):

```shell
uv run pytest
```

`DJANGO_SETTINGS_MODULE` is set to `django_project.settings.dev` for all tests. All DB tests use `@pytest.mark.django_db`.

## Running Locally (without Docker)

Seed the database:
```shell
uv run manage.py seed --mode=spawn_test_data
```

Run the hardware agent:
```shell
uv run manage.py run_hardware_agent
```

## Running with Docker Compose

```shell
docker compose up --watch --build
```

## Key Architecture Decisions

### Sensor Abstraction
All sensors inherit from `BaseSensor` (`src/hardware_agent/base.py`). Subclasses implement only `connect()`, `disconnect()`, `is_connected()`, and `poll()`. The base class handles background threading and automatic reconnection with 5-second retry backoff.

### Presence Period Grouping
RFID reads within 60 seconds of an existing period for the same chicken+box extend that period rather than creating a new one. Logic lives in `src/web_app/services/hardware_events.py`.

### Sensor Naming Convention
Sensors follow the pattern `{type}_{location}_{n}` (e.g. `rfid_left_1`, `beam_right`, `camera_cam`). The `_N` suffix is stripped to resolve the nesting box name.

### DB-Vendor Compatibility
Dashboard queries use PostgreSQL's `DISTINCT ON` when available, with a per-box loop fallback for SQLite (used in dev/test).

### Settings Split
`base.py` → `dev.py` (SQLite) / `prod.py` (PostgreSQL). Always use `dev` settings for tests.

## Key Models

- `Tag` — RFID tag
- `Chicken` — name, DoB, optional DoD, FK to Tag
- `NestingBox` — named box (e.g. "left", "right")
- `Egg` — FK to Chicken + NestingBox, `laid_at`, `quality` (saleable/edible/messy)
- `NestingBoxPresence` — individual RFID ping
- `NestingBoxPresencePeriod` — aggregated presence session (grouped within 60-second window)
- `NestingBoxImage` — timestamped JPEG snapshot
- `HardwareSensor` — live status tracking for each sensor

## Testing Patterns

- Use `factory-boy` factories from `test/web_app/factories.py` to create model instances
- Mock `django.utils.timezone.now` via `mocker.patch` to control time in period-grouping tests
- Mock hardware objects (serial ports, GPIO, OpenCV) rather than requiring physical devices
- Use `caplog` to assert on specific log messages and levels

## Management Commands

- `seed` — multi-mode: generate test data, clear data, or upsert from CSV files
  - `seed --mode=spawn_test_data --yes` — clear + repopulate with fake data (requires `DEBUG=True`)
  - `seed --mode=clear --yes` — wipe all app data
  - `seed --mode=seed_chickens` — upsert chickens from `chickens.csv`
  - `seed --mode=seed_tags` — upsert RFID tags from `tags.csv`
  - `seed --mode=seed_nesting_boxes` — ensure the standard nesting boxes exist
- `import_chickens` — alias for `seed --mode=seed_chickens`
- `import_tags` — alias for `seed --mode=seed_tags`
- `ensure_nesting_boxes` — alias for `seed --mode=seed_nesting_boxes` (idempotent, safe for deployment)
- `run_hardware_agent` — starts the hardware polling daemon
- `prune_nesting_box_images` — deletes images not near any presence period or egg (run nightly)
- `prune_nesting_box_images --all --yes` — deletes ALL images (requires explicit confirmation)

## Linting

```shell
uv run ruff check
uv run ruff format
```
