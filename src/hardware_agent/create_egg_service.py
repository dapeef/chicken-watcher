import time

from web_app.models import Egg, Chicken, NestingBox


def create_some_eggs():
    nesting_box = NestingBox.objects.all().first()
    chicken = Chicken.objects.all().first()

    for i in range(10):
        print(f"Creating egg number {i + 1}")
        Egg.objects.create(chicken=chicken, nesting_box=nesting_box)

        time.sleep(0.5)


if __name__ == "__main__":
    create_some_eggs()
