# Chicken watcher

## Overview

This is a system which will run on a Raspberry Pi and track which chicken lays which eggs.

## Dev

### Running locally

Seed the DB using:

```shell
uv run manage.py seed
```

Set the RFID readers' ports as environment variables. When deployed, these are set in the `.env` file and are set
by `docker_compose.yml`:

```shell
export RFID_SERIAL_PORT_LEFT=/dev/tty.usbserial-BG01PVA3
export RFID_SERIAL_PORT_RIGHT=/dev/...
```

Run the hardware agent using:

```shell
uv run manage.py run_hardware_agent
```

### Using `docker compose`

To run the project, run the following command. This will spin up the database, the python hardware script,
and the python web app.

```shell
docker compose up --watch --build
```

To view the logs of any container (in this case `hardware-agent`):

```shell
docker compose logs -f hardware-agent
```

## Prod

To run in production, we must exclude the `docker-compose.override.yml`:

```shell
docker compose -f docker-compose.yml up -d
```