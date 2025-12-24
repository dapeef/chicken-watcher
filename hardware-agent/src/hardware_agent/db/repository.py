from datetime import datetime, UTC

from .core import engine
from .schema import eggs


def insert_egg(hen_id: int, laid_at: datetime | None = None) -> None:
    """
    One INSERT, autocommit.
    """
    laid_at = laid_at or datetime.now(UTC)
    stmt = eggs.insert().values(hen_id=hen_id, laid_at=laid_at)

    # automatic transaction (commit/rollback) with begin()
    with engine.begin() as conn:
        conn.execute(stmt)


def get_last_eggs(limit: int = 20) -> list[dict]:
    """
    Return a list of dicts (for JSON serialization in the dashboard).
    """
    from sqlalchemy import select, desc

    stmt = (
        select(eggs.c.id, eggs.c.hen_id, eggs.c.laid_at)
        .order_by(desc(eggs.c.id))
        .limit(limit)
    )
    with engine.connect() as conn:
        result = conn.execute(stmt)
        return [dict(row._mapping) for row in result]
