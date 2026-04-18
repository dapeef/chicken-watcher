"""
Replace the boolean `dud` field on Egg with a `quality` CharField.

Data migration:
  dud=False  → quality='saleable'
  dud=True   → quality='messy'
"""

from django.db import migrations, models


def dud_to_quality(apps, schema_editor):
    Egg = apps.get_model("web_app", "Egg")
    Egg.objects.filter(dud=True).update(quality="messy")
    Egg.objects.filter(dud=False).update(quality="saleable")


def quality_to_dud(apps, schema_editor):
    """Reverse: anything that is not saleable becomes dud=True."""
    Egg = apps.get_model("web_app", "Egg")
    Egg.objects.filter(quality="saleable").update(dud=False)
    Egg.objects.exclude(quality="saleable").update(dud=True)


class Migration(migrations.Migration):
    dependencies = [
        ("web_app", "0019_remove_nestingboxpresenceperiod_sensor_id"),
    ]

    operations = [
        # 1. Add the new quality column with a temporary default so existing rows
        #    are valid before we run the data migration.
        migrations.AddField(
            model_name="egg",
            name="quality",
            field=models.CharField(
                max_length=10,
                choices=[
                    ("saleable", "Saleable"),
                    ("edible", "Edible"),
                    ("messy", "Messy"),
                ],
                default="saleable",
            ),
            preserve_default=False,
        ),
        # 2. Populate quality from the existing dud column.
        migrations.RunPython(dud_to_quality, reverse_code=quality_to_dud),
        # 3. Add the DB index now that values are consistent.
        migrations.AddIndex(
            model_name="egg",
            index=models.Index(fields=["quality"], name="web_app_egg_quality_idx"),
        ),
        # 4. Drop the old dud column.
        migrations.RemoveField(
            model_name="egg",
            name="dud",
        ),
    ]
