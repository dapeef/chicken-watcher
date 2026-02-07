FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# --- system packages to help with image processing -----------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0                    \
        swig python3-dev build-essential       \
        wget                                   \
    && rm -rf /var/lib/apt/lists/*

# Install lgpio C library from source
RUN wget https://github.com/joan2937/lg/archive/master.zip -O lg.zip && \
    apt-get update && apt-get install -y unzip && \
    unzip lg.zip && \
    cd lg-master && \
    make && \
    make install && \
    ldconfig && \
    cd .. && \
    rm -rf lg-master lg.zip && \
    apt-get remove -y unzip wget && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

## Pull images from piwheels to save building them on the pi
#ENV UV_EXTRA_INDEX_URL=https://www.piwheels.org/simple
#ENV UV_INDEX=https://www.piwheels.org/simple
#ENV UV_INDEX_STRATEGY=unsafe-best-match

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
# Don't buffer python logs; print them immediately
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
     uv sync --no-install-project

# Copy over the source files
COPY ./src ./src
COPY manage.py ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync

CMD  ["bash", "-c", "\
      uv run manage.py migrate --no-input && \
      uv run manage.py collectstatic --no-input --clear && \
      uv run uvicorn django_project.asgi:application --host 0.0.0.0 --port 8000 --workers 1"]
