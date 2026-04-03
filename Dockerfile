########################################
# 1.  Build stage
########################################
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# --- system packages needed for compiling --------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential swig python3-dev wget unzip \
    && rm -rf /var/lib/apt/lists/*

# --- build and install lgpio ---------------------------------------
RUN wget -q https://github.com/joan2937/lg/archive/master.zip -O /tmp/lg.zip && \
    unzip -q /tmp/lg.zip -d /tmp && \
    make -C /tmp/lg-master && \
    make -C /tmp/lg-master install && \
    ldconfig

# --- UV / Python settings ------------------------------------------
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# lock-file first for maximised layer-caching
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

########################################
# 1.5. Build project
########################################
FROM builder AS project-builder

# project sources
COPY src ./src
COPY manage.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync


########################################
# 2.  Runtime stage
########################################
FROM python:3.13-slim-bookworm AS runtime

# only the *runtime* Debian libs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# copy the lgpio shared objects and python site-packages
COPY --from=builder /usr/local/lib /usr/local/lib
COPY --from=builder /usr/local/bin /usr/local/bin

# make the dynamic linker aware of /usr/local/lib
RUN ldconfig

# copy application code (already byte-compiled)
COPY --from=builder /app/.venv /app/.venv
COPY --from=project-builder /app/src /app/src
COPY --from=project-builder /app/manage.py /app/manage.py
COPY --from=project-builder /app/pyproject.toml /app/uv.lock ./

CMD ["bash", "-c", "\
      python manage.py migrate --no-input && \
      python manage.py collectstatic --no-input --clear && \
      uvicorn django_project.asgi:application --host 0.0.0.0 --port 8000 --workers 3"]

########################################
# 3.  Scheduler stage
########################################
FROM runtime AS scheduler

RUN apt-get update && \
    apt-get install -y --no-install-recommends cron && \
    rm -rf /var/lib/apt/lists/*

COPY scheduler/crontab /app/crontab

CMD ["sh", "-c", \
    "{ printenv | grep -E '^(DJANGO_|POSTGRES_|MEDIA_ROOT|LOG_FILENAME)'; cat /app/crontab; } | crontab - \
    && exec cron -f -L /dev/stdout"]
