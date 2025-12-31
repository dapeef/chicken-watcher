FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy
# Disable Python downloads, because we want to use the system interpreter
# across both images. If using a managed Python version, it needs to be
# copied from the build image into the final image; see `standalone.Dockerfile`
# for an example.
ENV UV_PYTHON_DOWNLOADS=0
## Omit development dependencies
ENV UV_NO_DEV=1

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# Copy over the source files
COPY ./src ./src
COPY manage.py ./

# Rebuild to include source files; helps Docker with cache hits
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked


### Runtime ###
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime

# --- system packages -----------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1           \
        libglib2.0-0     \
    && rm -rf /var/lib/apt/lists/*

# Copy the application from the builder
COPY --from=builder /app /app

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Don't buffer python logs; print them immediately
ENV PYTHONUNBUFFERED=1

WORKDIR /app

CMD  ["bash", "-c", "\
      uv run manage.py migrate --no-input && \
      uv run python manage.py collectstatic --no-input --clear && \
      uv run uvicorn django_project.asgi:application --host 0.0.0.0 --port 8000 --workers 1"]
