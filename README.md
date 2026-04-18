# Chicken Watcher

A Raspberry Pi IoT system that tracks which chicken lays which eggs in a chicken coop. Two processes run side by side: a Django web app (UI + data store) and a hardware polling daemon that reads RFID tags, a camera, and beam-break sensors.

## Architecture

Four Docker Compose services:

| Service | What it does |
|---|---|
| `db` | Postgres 16 — all persistent state |
| `web-app` | Django/Uvicorn on port 8000. Serves the UI. Runs `migrate` and `collectstatic` automatically on startup. |
| `hardware-agent` | Polls RFID readers, camera, and beam sensors. Writes events to the DB. Starts only once `web-app` is healthy. |
| `scheduler` | Cron container. Runs `prune_nesting_box_images` at midnight every night. |

The app is **intentionally LAN-only** with no authentication. Access it at `http://<pi-ip>:8000` from your home network, or via VPN into the LAN from outside.

---

## Setting up the Pi for the first time

### 1. Install prerequisites

```shell
sudo apt install micro tree btop
curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
sudo usermod -aG docker ${USER}
# log out and back in for the group change to take effect
```

### 2. Clone the repo

```shell
git clone <repo-url>
cd chicken-watcher
```

### 3. Configure environment variables

```shell
cp .env.example .env
micro .env
```

Fill in every field. The minimum required set:

```
POSTGRES_DB=chickens
POSTGRES_USER=chicken
POSTGRES_PASSWORD=<strong password>
DJANGO_SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_urlsafe(50))">

COOP_LATITUDE=<your latitude>
COOP_LONGITUDE=<your longitude>
```

Hardware fields — leave blank for any sensor that isn't connected (it will be skipped gracefully):

```
# Use stable by-id paths, not /dev/ttyUSB0, so they survive reboots
RFID_PORT_LEFT_1=/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG01PVA3-if00-port0
RFID_PORT_LEFT_2=
...
CAMERA_DEVICE=/dev/v4l/by-id/usb-Arducam_...
BEAM_BREAK_GPIO_LEFT=17
BEAM_BREAK_GPIO_RIGHT=27
```

To find device paths:
```shell
ls -l /dev/serial/by-id/    # RFID readers
ls -l /dev/v4l/by-id/       # cameras
```

### 4. Start the containers

```shell
docker compose up -d --build
```

Migrations and static-file collection run automatically inside `web-app` on first start.

### 5. One-time data setup

```shell
# Create the left and right nesting boxes (idempotent — safe to re-run)
docker compose exec web-app python manage.py ensure_nesting_boxes

# Import your RFID tags from tags.csv
docker compose exec web-app python manage.py import_tags

# Import your chickens from chickens.csv (tags must exist first)
docker compose exec web-app python manage.py import_chickens
```

The CSV files live at `src/web_app/management/commands/chickens.csv` and `tags.csv`. Edit them to match your flock before importing.

---

## Day-to-day operations

### Start / stop

```shell
docker compose up -d          # start all services in the background
docker compose down           # stop everything cleanly (data is preserved in volumes)
docker compose restart web-app  # restart a single service
```

### Update after a code change

```shell
docker compose up -d --build
```

Migrations run automatically on startup — no separate step needed.

---

## Viewing logs

### Live container output

```shell
docker compose logs -f web-app
docker compose logs -f hardware-agent
docker compose logs -f scheduler
```

### Log files (in the mounted logs volume)

Each service writes to a rotating log file. To browse them:

```shell
# Shell into a temporary container with the logs volume mounted
docker run --rm -it -v chicken-watcher_logs_volume:/app/logs alpine sh
ls /app/logs
```

Files are named by the `LOG_FILENAME` env var set in `docker-compose.yml`:
- `web_app.log` — Django web requests and app events
- `hardware_agent.log` — sensor connections, RFID reads, beam breaks
- `scheduler.log` — nightly prune job output

Log level defaults to `INFO`. To get verbose debug output for a service, add `LOG_LEVEL=DEBUG` to its environment in `docker-compose.yml` (or `.env`) and restart.

---

## Management commands

Run any command with:
```shell
docker compose exec web-app python manage.py <command>
```

### Data import (non-destructive, idempotent)

| Command | What it does |
|---|---|
| `ensure_nesting_boxes` | Create the standard left/right nesting boxes if they don't exist. Safe to run any time. |
| `import_chickens [--csv-file path]` | Upsert chickens from `chickens.csv` (or a custom path). |
| `import_tags [--csv-file path]` | Upsert RFID tags from `tags.csv`. |

### Image cleanup

| Command | What it does |
|---|---|
| `prune_nesting_box_images` | Delete camera frames with no egg or presence period within 30 seconds. Runs automatically at midnight via cron. |
| `prune_nesting_box_images --all --yes` | Delete **every** camera frame. Requires `--yes`. |

### Destructive (require `--yes`)

| Command | What it does |
|---|---|
| `seed --mode=clear --yes` | Wipe all app data (chickens, eggs, presence, images). |
| `seed --mode=spawn_test_data --yes` | Wipe and repopulate with fake test data. Also requires the container to have `DEBUG=True` — prod containers refuse this. |

---

## Local development (without Docker)

```shell
# Install dependencies
uv sync

# Run migrations against the local SQLite DB
uv run manage.py migrate

# Seed with fake data for development
uv run manage.py seed --mode=spawn_test_data --yes

# Start the web server
uv run manage.py runserver

# Start the hardware agent (only useful if sensors are physically connected)
uv run manage.py run_hardware_agent
```

### Tests

```shell
uv run pytest
```

Tests always use SQLite with `dev` settings — no env vars needed.

### Lint and format

```shell
uv run ruff check        # lint
uv run ruff check --fix  # lint + auto-fix
uv run ruff format       # reformat
```

---

## Environment variable reference

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | **Yes (prod)** | insecure dev fallback | Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ENV` | No | `prod` | Set to `dev` for local development without Docker. |
| `POSTGRES_DB` | **Yes** | — | |
| `POSTGRES_USER` | **Yes** | — | |
| `POSTGRES_PASSWORD` | **Yes** | — | |
| `POSTGRES_HOST` | No | `db` | Matches the Compose service name. Change only if DB runs elsewhere. |
| `COOP_LATITUDE` | No | `51.5` | Used for sunrise/sunset shading on the timeline. |
| `COOP_LONGITUDE` | No | `-0.1` | |
| `MEDIA_ROOT` | No | `<repo>/media` | Set to `/app/media` in Docker (mounted volume). |
| `STATIC_ROOT` | No | `<repo>/static` | Set to `/app/static` in Docker (mounted volume). |
| `LOG_DIR` | No | `<repo>/logs` | Log file directory. Set to `/app/logs` in Docker. |
| `LOG_FILENAME` | No | `django.log` | Each Compose service overrides this to its own filename. |
| `LOG_LEVEL` | No | `INFO` | Set to `DEBUG` for verbose logging. |
| `DJANGO_DB_LOG_LEVEL` | No | `INFO` | Set to `DEBUG` to echo every SQL query. |
| `RFID_PORT_LEFT_1..4` | No | — | Serial port path per reader. Blank = skip. |
| `RFID_PORT_RIGHT_1..4` | No | — | |
| `CAMERA_DEVICE` | No | — | Camera device path. Blank = no camera. |
| `BEAM_BREAK_GPIO_LEFT` | No | — | GPIO pin number for the left box beam sensor. |
| `BEAM_BREAK_GPIO_RIGHT` | No | — | GPIO pin number for the right box beam sensor. |

---

## Key things to know

- **Migrations run automatically** on every `web-app` startup. You don't need to run them after an update.
- **Sensors that aren't configured are skipped gracefully.** You'll see a warning in the logs and a "Disconnected" badge on the dashboard. The app keeps running.
- **`DJANGO_ENV` defaults to `prod`**, so forgetting to set it gives you Postgres + `DEBUG=False` rather than silently falling back to SQLite. This is intentional.
- **The `hardware-agent` waits for `web-app` to be healthy** before starting. On a Pi 3 this can take up to a minute on first boot.
- **Camera frames are pruned nightly.** Only frames within 30 seconds of a presence period or egg event are kept. To pause cleanup, stop the scheduler service: `docker compose stop scheduler`.
- **There is no login screen.** The LAN + VPN boundary is the access control. Don't expose port 8000 to the public internet.
