## Description

A python app which handles the hardware in the chicken monitor application:
- Reads RFID leg tags
- Watches for the beam-break in the egg-chute
- Reads the egg weighing scale

It writes to the associated database.

## To run the app

```shell
uv run hardware-agent
```

## To run tests

```shell
uv run pytest
```

## To lint and format

```shell
uv run ruff format
uv run ruff check --fix
```
