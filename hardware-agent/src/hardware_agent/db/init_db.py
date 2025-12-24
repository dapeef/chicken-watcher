from .core import engine
from .schema import metadata


def create_schema() -> None:
    metadata.create_all(engine)  # idempotent


if __name__ == "__main__":
    create_schema()
