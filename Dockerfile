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
#ENV UV_NO_DEV=1

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

# Setup a non-root user
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot

# Copy the application from the builder
COPY --from=builder --chown=nonroot:nonroot /app /app

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Don't buffer python logs; print them immediately
ENV PYTHONUNBUFFERED=1

# Use the non-root user to run our application
USER nonroot

WORKDIR /app

RUN uv run manage.py migrate

CMD  ["uv", "run", "manage.py", "run_hardware_agent"]
