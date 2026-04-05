"""Unit tests for web_app.views.timeline_utils serialiser helpers."""

import pytest
from datetime import timedelta
from django.utils import timezone

from web_app.views.timeline_utils import egg_item, period_item, presence_item
from ..factories import (
    ChickenFactory,
    EggFactory,
    NestingBoxFactory,
    NestingBoxPresenceFactory,
    NestingBoxPresencePeriodFactory,
)


@pytest.mark.django_db
class TestEggItem:
    def test_basic_fields(self):
        egg = EggFactory()
        item = egg_item(egg)
        assert item["id"] == f"egg_{egg.id}"
        assert item["content"] == "🥚"
        assert item["start"] == egg.laid_at.isoformat()

    def test_non_dud_has_base_class_only(self):
        egg = EggFactory(dud=False)
        item = egg_item(egg)
        assert item["className"] == "timeline-egg"
        assert "dud" not in item["className"]

    def test_dud_has_dud_class(self):
        egg = EggFactory(dud=True)
        item = egg_item(egg)
        assert "timeline-egg" in item["className"]
        assert "timeline-egg--dud" in item["className"]

    def test_include_group_false_omits_group(self):
        egg = EggFactory()
        item = egg_item(egg, include_group=False)
        assert "group" not in item

    def test_include_group_true_with_chicken(self):
        chicken = ChickenFactory()
        egg = EggFactory(chicken=chicken)
        item = egg_item(egg, include_group=True)
        assert item["group"] == f"chicken_{chicken.pk}"

    def test_include_group_true_without_chicken(self):
        egg = EggFactory(chicken=None)
        item = egg_item(egg, include_group=True)
        assert item["group"] == "unknown"

    def test_dud_with_include_group(self):
        chicken = ChickenFactory()
        egg = EggFactory(chicken=chicken, dud=True)
        item = egg_item(egg, include_group=True)
        assert "timeline-egg--dud" in item["className"]
        assert item["group"] == f"chicken_{chicken.pk}"


@pytest.mark.django_db
class TestPeriodItem:
    def test_basic_fields(self):
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            started_at=now, ended_at=now + timedelta(minutes=5)
        )
        item = period_item(period)
        assert item["id"] == f"period_{period.id}"
        assert item["start"] == period.started_at.isoformat()
        assert item["end"] == period.ended_at.isoformat()
        assert item["type"] == "range"

    def test_class_name_contains_box_name(self):
        box = NestingBoxFactory(name="left")
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            nesting_box=box, started_at=now, ended_at=now + timedelta(minutes=1)
        )
        item = period_item(period)
        assert "timeline-period" in item["className"]
        assert "box-left" in item["className"]

    def test_include_group_false_omits_group(self):
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            started_at=now, ended_at=now + timedelta(minutes=1)
        )
        item = period_item(period, include_group=False)
        assert "group" not in item

    def test_include_group_true_sets_group(self):
        chicken = ChickenFactory()
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            chicken=chicken, started_at=now, ended_at=now + timedelta(minutes=1)
        )
        item = period_item(period, include_group=True)
        assert item["group"] == f"chicken_{chicken.pk}"

    def test_content_includes_box_name(self):
        box = NestingBoxFactory(name="right")
        now = timezone.now()
        period = NestingBoxPresencePeriodFactory(
            nesting_box=box, started_at=now, ended_at=now + timedelta(minutes=1)
        )
        item = period_item(period)
        assert "right" in item["content"]


@pytest.mark.django_db
class TestPresenceItem:
    def test_basic_fields(self):
        presence = NestingBoxPresenceFactory()
        item = presence_item(presence)
        assert item["id"] == f"presence_{presence.id}"
        assert item["start"] == presence.present_at.isoformat()
        assert item["type"] == "point"

    def test_class_name_contains_box_name(self):
        box = NestingBoxFactory(name="left")
        presence = NestingBoxPresenceFactory(nesting_box=box)
        item = presence_item(presence)
        assert "timeline-presence-dot" in item["className"]
        assert "box-left" in item["className"]

    def test_group_is_always_set(self):
        chicken = ChickenFactory()
        presence = NestingBoxPresenceFactory(chicken=chicken)
        item = presence_item(presence)
        assert item["group"] == f"chicken_{chicken.pk}"

    def test_content_is_empty(self):
        presence = NestingBoxPresenceFactory()
        item = presence_item(presence)
        assert item["content"] == ""
