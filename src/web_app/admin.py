from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Chicken,
    Egg,
    HardwareSensor,
    NestingBox,
    NestingBoxImage,
    NestingBoxPresence,
    NestingBoxPresencePeriod,
    Tag,
)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("number", "rfid_string")
    search_fields = ("rfid_string", "number")
    ordering = ("number",)


@admin.register(Chicken)
class ChickenAdmin(admin.ModelAdmin):
    list_display = ("name", "date_of_birth", "date_of_death", "tag_number", "is_alive")
    list_filter = ("date_of_death",)
    search_fields = ("name", "tag__rfid_string")
    autocomplete_fields = ("tag",)
    list_select_related = ("tag",)
    ordering = ("name",)

    @admin.display(description="Tag #", ordering="tag__number")
    def tag_number(self, obj):
        return obj.tag.number if obj.tag else "—"

    @admin.display(description="Alive?", boolean=True)
    def is_alive(self, obj):
        return obj.date_of_death is None


@admin.register(NestingBox)
class NestingBoxAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Egg)
class EggAdmin(admin.ModelAdmin):
    list_display = ("__str__", "quality", "laid_at", "chicken", "nesting_box")
    list_filter = ("quality", "nesting_box")
    search_fields = ("chicken__name",)
    autocomplete_fields = ("chicken", "nesting_box")
    list_select_related = ("chicken", "nesting_box")
    date_hierarchy = "laid_at"
    ordering = ("-laid_at",)


@admin.register(NestingBoxPresencePeriod)
class NestingBoxPresencePeriodAdmin(admin.ModelAdmin):
    list_display = ("chicken", "nesting_box", "started_at", "ended_at", "duration_display")
    list_filter = ("nesting_box", "chicken")
    search_fields = ("chicken__name",)
    list_select_related = ("chicken", "nesting_box")
    date_hierarchy = "started_at"
    ordering = ("-started_at",)

    @admin.display(description="Duration")
    def duration_display(self, obj):
        d = obj.duration
        total_seconds = int(d.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"


@admin.register(NestingBoxPresence)
class NestingBoxPresenceAdmin(admin.ModelAdmin):
    list_display = ("chicken", "nesting_box", "present_at", "sensor_id")
    list_filter = ("nesting_box",)
    search_fields = ("chicken__name", "sensor_id")
    list_select_related = ("chicken", "nesting_box")
    raw_id_fields = ("presence_period",)
    date_hierarchy = "present_at"
    ordering = ("-present_at",)


@admin.register(NestingBoxImage)
class NestingBoxImageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "thumbnail")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:60px; max-width:80px;">',
                obj.image.url,
            )
        return "—"


@admin.register(HardwareSensor)
class HardwareSensorAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "last_event_at", "last_seen_at", "status_message")
    list_filter = ("status",)
    search_fields = ("name",)
    readonly_fields = ("last_seen_at",)
    ordering = ("name",)
