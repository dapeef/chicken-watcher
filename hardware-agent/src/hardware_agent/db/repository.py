import uuid

from datetime import datetime, UTC

from .core import engine
from .schema import eggs, chickens


def insert_egg(chicken_id: int, laid_at: datetime | None = None) -> None:
    """
    One INSERT, autocommit.
    """
    laid_at = laid_at or datetime.now(UTC)
    stmt = eggs.insert().values(chicken_id=chicken_id, laid_at=laid_at)

    # automatic transaction (commit/rollback) with begin()
    with engine.begin() as conn:
        conn.execute(stmt)


def insert_chicken(
    name: str,
    date_of_birth: datetime | None = None,
    date_of_death: datetime | None = None,
    tag_string: str | None = None,
) -> None:
    """
    One INSERT, autocommit.
    """
    date_of_birth = date_of_birth or datetime.now(UTC)

    tag_string = tag_string or str(uuid.uuid4())

    stmt = chickens.insert().values(
        name=name,
        date_of_birth=date_of_birth,
        date_of_death=date_of_death,
        tag_string=tag_string,
    )

    # automatic transaction (commit/rollback) with begin()
    with engine.begin() as conn:
        conn.execute(stmt)


def get_last_eggs(limit: int = 20) -> list[dict]:
    """
    Return a list of dicts (for JSON serialization in the dashboard).
    """
    from sqlalchemy import select, desc

    stmt = (
        select(eggs.c.id, eggs.c.chicken_id, eggs.c.laid_at)
        .order_by(desc(eggs.c.id))
        .limit(limit)
    )
    with engine.connect() as conn:
        result = conn.execute(stmt)
        return [dict(row._mapping) for row in result]
