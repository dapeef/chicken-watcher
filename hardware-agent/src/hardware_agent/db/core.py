from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool  # light weight on Pi; switch later

POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")

POSTGRES_DSN = (
    f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@db/{POSTGRES_DB}"
)

engine = create_engine(
    POSTGRES_DSN,
    future=True,  # enables the 2.x style
    echo=False,  # flip to True while debugging SQL
    poolclass=NullPool,  # or pool_size=5 if you prefer a pool
)
