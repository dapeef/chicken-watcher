from .schema import chickens
from .core import engine
from .repository import insert_chicken, insert_egg
from .init_db import create_schema

from sqlalchemy import select


def main() -> None:
    create_schema()  # idempotent – does nothing if tables exist

    # Check whether the db has already been seeded, to prevent seeding duplicates
    with engine.connect() as conn:
        already_seeded = conn.scalar(select(chickens.c.id).limit(1)) is not None

    if not already_seeded:
        seed_db()


def seed_db() -> None:
    insert_chicken("Scramble")
    insert_chicken("Omelette")

    insert_egg(2)

    print("💾 Dev data inserted")


if __name__ == "__main__":
    main()
