"""
Enforce "at most one *live* chicken per RFID tag" at the DB layer.

Migration 0015 originally declared Chicken.tag as OneToOneField; 0016
silently weakened it to ForeignKey, which allowed two chickens to
claim the same tag. The hardware-agent handler filters by
``date_of_death__isnull=True`` to resolve ambiguity, but nothing
stopped the underlying data from drifting into a multi-claim state.

We keep ForeignKey (so tags can be reassigned when a chicken dies) but
add a partial UniqueConstraint that enforces uniqueness only across
live chickens with a non-null tag. Dead chickens retain their
historical tag for provenance, and freed tags can be reassigned.

If pre-existing data violates this constraint, the migration will
fail; inspect for duplicates and resolve them with a data migration
first.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("web_app", "0022_presence_period_time_ordering"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="chicken",
            constraint=models.UniqueConstraint(
                condition=models.Q(("date_of_death__isnull", True), ("tag__isnull", False)),
                fields=("tag",),
                name="unique_tag_per_live_chicken",
            ),
        ),
    ]
