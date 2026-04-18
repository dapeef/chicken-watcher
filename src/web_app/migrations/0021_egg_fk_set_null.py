"""
Change Egg.chicken and Egg.nesting_box to on_delete=SET_NULL.

Previously both FKs were CASCADE, meaning deleting a chicken or nesting box
would silently obliterate every egg associated with it. Both fields are
already nullable (null=True, blank=True), so SET_NULL is the safe choice:
historical egg records are preserved and simply lose their chicken/box
association when the referenced row is removed.

Also reconciles the Egg.quality index: migration 0020 added an explicit
AddIndex operation, but the model declares db_index=True directly on the
field. These are equivalent at the DB level but appear as drift in Django's
migration state. Remove the explicit index and re-declare it via the field
so future makemigrations runs stay clean.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("web_app", "0020_egg_quality"),
    ]

    operations = [
        migrations.AlterField(
            model_name="egg",
            name="chicken",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="web_app.chicken",
            ),
        ),
        migrations.AlterField(
            model_name="egg",
            name="nesting_box",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="web_app.nestingbox",
            ),
        ),
        # Reconcile index drift from 0020: remove the explicit index
        # and re-declare it as db_index=True on the field (functionally
        # identical, but matches the model declaration).
        migrations.RemoveIndex(
            model_name="egg",
            name="web_app_egg_quality_idx",
        ),
        migrations.AlterField(
            model_name="egg",
            name="quality",
            field=models.CharField(
                choices=[
                    ("saleable", "Saleable"),
                    ("edible", "Edible"),
                    ("messy", "Messy"),
                ],
                db_index=True,
                default="saleable",
                max_length=10,
            ),
        ),
    ]
