"""
Add sensible default orderings to every model.

Previously most models had no ``Meta.ordering``, which meant:

* Every view and template had to specify ``order_by(...)`` explicitly or
  inherit implementation-defined DB insertion order.
* Tests that accidentally relied on insertion order were portable only
  by luck.

Orderings chosen to match what views were already requesting:

* ``Tag`` → by number (human-friendly ID)
* ``Chicken`` → by name (alphabetical, matches ChickenListView default)
* ``Egg`` → by ``-laid_at`` (newest first, matches EggListView)
* ``NestingBoxPresence`` → by ``-present_at`` (newest first)
* ``NestingBoxPresencePeriod`` → by ``-started_at`` (newest first)
* ``NestingBoxImage`` → by ``-created_at`` (newest first)
* ``NestingBox`` → by name
* ``HardwareSensor`` → by name

This is purely metadata: no table or index changes.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("web_app", "0023_unique_tag_per_live_chicken"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="chicken",
            options={"ordering": ["name"]},
        ),
        migrations.AlterModelOptions(
            name="egg",
            options={"ordering": ["-laid_at"]},
        ),
        migrations.AlterModelOptions(
            name="hardwaresensor",
            options={"ordering": ["name"]},
        ),
        migrations.AlterModelOptions(
            name="nestingbox",
            options={"ordering": ["name"], "verbose_name_plural": "nesting boxes"},
        ),
        migrations.AlterModelOptions(
            name="nestingboximage",
            options={"ordering": ["-created_at"]},
        ),
        migrations.AlterModelOptions(
            name="nestingboxpresence",
            options={"ordering": ["-present_at"]},
        ),
        migrations.AlterModelOptions(
            name="nestingboxpresenceperiod",
            options={"ordering": ["-started_at"]},
        ),
        migrations.AlterModelOptions(
            name="tag",
            options={"ordering": ["number"]},
        ),
    ]
