import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_project.settings")
django.setup()

# Must be below `django.setup()` for the imports to work correctly
from web_app.models import Egg, Chicken, NestingBox  # noqa: E402


def main():
    nesting_box = NestingBox.objects.all().first()
    chicken = Chicken.objects.all().first()

    for i in range(10):
        print(f"Creating egg number {i + 1}")
        Egg.objects.create(chicken=chicken, nesting_box=nesting_box)


if __name__ == "__main__":
    main()
