"""Unit tests for web_app.views.timeline_utils serialiser helpers."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from web_app.views.timeline_utils import (
    egg_item,
    night_periods,
    period_item,
    presence_item,
)

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

    def test_saleable_egg_has_saleable_class(self):
        egg = EggFactory(quality="saleable")
        item = egg_item(egg)
        assert "timeline-egg" in item["className"]
        assert "timeline-egg--saleable" in item["className"]

    def test_edible_egg_has_edible_class(self):
        egg = EggFactory(quality="edible")
        item = egg_item(egg)
        assert "timeline-egg" in item["className"]
        assert "timeline-egg--edible" in item["className"]

    def test_messy_egg_has_messy_class(self):
        egg = EggFactory(quality="messy")
        item = egg_item(egg)
        assert "timeline-egg" in item["className"]
        assert "timeline-egg--messy" in item["className"]

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

    def test_messy_with_include_group(self):
        chicken = ChickenFactory()
        egg = EggFactory(chicken=chicken, quality="messy")
        item = egg_item(egg, include_group=True)
        assert "timeline-egg--messy" in item["className"]
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

    def test_no_sensor_id_omits_sensor_class(self):
        """When sensor_id is empty, no sensor-* class is added."""
        box = NestingBoxFactory(name="left")
        presence = NestingBoxPresenceFactory(nesting_box=box, sensor_id="")
        item = presence_item(presence)
        assert "sensor-" not in item["className"]

    def test_sensor_id_adds_sensor_class(self):
        """When sensor_id is set, a sensor-* CSS class is added."""
        box = NestingBoxFactory(name="left")
        presence = NestingBoxPresenceFactory(nesting_box=box, sensor_id="left_1")
        item = presence_item(presence)
        assert "sensor-left-1" in item["className"]

    def test_sensor_id_underscore_replaced_with_hyphen(self):
        """Underscores in sensor_id are replaced with hyphens for valid CSS."""
        box = NestingBoxFactory(name="left")
        presence = NestingBoxPresenceFactory(nesting_box=box, sensor_id="left_2")
        item = presence_item(presence)
        assert "sensor-left-2" in item["className"]
        assert "sensor-left_2" not in item["className"]

    def test_sensor_id_class_alongside_box_class(self):
        """Both box-* and sensor-* classes are present when sensor_id is set."""
        box = NestingBoxFactory(name="left")
        presence = NestingBoxPresenceFactory(nesting_box=box, sensor_id="left_1")
        item = presence_item(presence)
        assert "box-left" in item["className"]
        assert "sensor-left-1" in item["className"]
        assert "timeline-presence-dot" in item["className"]

    def test_all_four_sensors_have_distinct_css_classes(self):
        """All four sensors in a box get distinct CSS classes for individual colouring."""
        box = NestingBoxFactory(name="left")
        presences = [
            NestingBoxPresenceFactory(nesting_box=box, sensor_id=f"left_{n}")
            for n in range(1, 5)
        ]
        items = [presence_item(p) for p in presences]
        class_names = [i["className"] for i in items]
        # All four class strings are distinct
        assert len(set(class_names)) == 4
        for n in range(1, 5):
            assert f"sensor-left-{n}" in class_names[n - 1]


class TestNightPeriods:
    """Tests for the night_periods() helper."""

    def _window(self, days=1):
        """Return a (start, end) window spanning ``days`` days from midnight today."""
        start = datetime(2024, 6, 21, 0, 0, 0, tzinfo=UTC)
        end = start + timedelta(days=days)
        return start, end

    def test_returns_list(self):
        start, end = self._window()
        result = night_periods(start, end)
        assert isinstance(result, list)

    def test_each_item_has_required_keys(self):
        start, end = self._window()
        items = night_periods(start, end)
        assert len(items) >= 1
        for item in items:
            assert item["type"] == "background"
            assert item["className"] == "timeline-night"
            assert "id" in item
            assert "start" in item
            assert "end" in item

    def test_night_start_before_night_end(self):
        """Sunset must come before next sunrise."""
        start, end = self._window()
        for item in night_periods(start, end):
            assert item["start"] < item["end"]

    def test_all_items_overlap_window(self):
        """Every returned band must overlap the requested window."""
        start, end = self._window()
        for item in night_periods(start, end):
            band_start = item["start"]
            band_end = item["end"]
            assert band_end > start.isoformat()
            assert band_start < end.isoformat()

    def test_multi_day_window_returns_multiple_bands(self):
        """A week-long window should produce ~7 night bands."""
        start, end = self._window(days=7)
        items = night_periods(start, end)
        assert len(items) >= 6  # at minimum one per day

    def test_unique_ids(self):
        """Each band must have a unique id."""
        start, end = self._window(days=7)
        items = night_periods(start, end)
        ids = [i["id"] for i in items]
        assert len(ids) == len(set(ids))

    def test_returns_empty_when_lat_lon_missing(self):
        """Returns [] gracefully when settings have no location configured."""
        start, end = self._window()
        with patch("web_app.views.timeline_utils.settings") as mock_settings:
            del mock_settings.COOP_LATITUDE
            mock_settings.COOP_LATITUDE = None
            mock_settings.COOP_LONGITUDE = None
            result = night_periods(start, end)
        assert result == []

    @pytest.mark.django_db
    def test_timeline_data_includes_night_bands(self, client):
        """The timeline_data endpoint includes night background items."""
        from django.urls import reverse

        start = datetime(2024, 6, 21, 0, 0, 0, tzinfo=UTC)
        end = start + timedelta(days=1)
        url = reverse("timeline_data")
        response = client.get(f"{url}?start={start.isoformat()}&end={end.isoformat()}")
        assert response.status_code == 200
        data = response.json()
        night_items = [i for i in data if i.get("type") == "background"]
        assert len(night_items) >= 1
        assert all(i["className"] == "timeline-night" for i in night_items)
