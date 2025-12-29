#!/usr/bin/env sh
set -e                                   # fail on first error

# 1. run migrations (idempotent)
uv run manage.py migrate --noinput

# 2. hand control over to the main container command
exec "$@"
