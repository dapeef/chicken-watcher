# Chicken watcher

## Overview

This is a system which will run on a Raspberry Pi and track which chicken lays which eggs.

## Dev

To run the project, run the following command. This will spin up the database and the python hardware script.

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