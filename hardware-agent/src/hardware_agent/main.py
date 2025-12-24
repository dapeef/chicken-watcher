from .db.repository import insert_egg
from .db.init_db import create_schema
import time


def main() -> None:
    print("Hello from hardware-agent!")

    print("Creating schema...")
    create_schema()

    print("Inserting eggs...")
    for i in range(10):
        time.sleep(1)
        # print(f"Creating egg {i}...")
        insert_egg(i)

    print(f"Just inserted {i + 1} eggs")


if __name__ == "__main__":
    main()
