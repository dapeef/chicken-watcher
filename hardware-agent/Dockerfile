FROM python:3.13-slim-bookworm

RUN  pip install --no-cache-dir uv

COPY . .

CMD  ["uv", "run", "main.py"]
