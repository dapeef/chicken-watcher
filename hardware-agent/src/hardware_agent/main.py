from .db.repository import insert_egg, get_chicken_id_by_tag
from .db.init_db import create_schema
import time


def main() -> None:
    print("Hello from hardware-agent!")

    print("Creating schema...")
    create_schema()

    print("Inserting eggs...")
    for i in range(10):
        time.sleep(1)
        chicken_id = get_chicken_id_by_tag("abc")
        print("Chicken id:", chicken_id)
        insert_egg(chicken_id=chicken_id)

    print(f"Just inserted {i + 1} eggs")


if __name__ == "__main__":
    main()
