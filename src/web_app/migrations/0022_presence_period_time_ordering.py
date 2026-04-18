"""
Re-add the ``started_at <= ended_at`` check constraint on
NestingBoxPresencePeriod.

This constraint existed on the original ``NestingBoxVisit`` model
(see migration 0001) but was silently dropped when the table was renamed
to ``NestingBoxPresencePeriod`` in migration 0011. The period-grouping
logic in handle_tag_read always sets ``ended_at >= started_at``, so this
is restoring an invariant the model already holds at the application
layer; the DB-level check catches regressions.

If any pre-existing rows violate the invariant (none expected — seed
data always uses ended_at >= started_at), Postgres/SQLite will fail the
migration; fix them with a data migration first if that happens.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("web_app", "0021_egg_fk_set_null"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="nestingboxpresenceperiod",
            constraint=models.CheckConstraint(
                condition=models.Q(("ended_at__gte", models.F("started_at"))),
                name="presence_period_started_before_ended",
            ),
        ),
    ]
