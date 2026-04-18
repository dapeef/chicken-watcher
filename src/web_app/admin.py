from django.contrib import admin

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

admin.site.register(Tag)
admin.site.register(Chicken)
admin.site.register(NestingBox)
admin.site.register(Egg)
admin.site.register(NestingBoxPresence)
admin.site.register(NestingBoxImage)
admin.site.register(HardwareSensor)
admin.site.register(NestingBoxPresencePeriod)
