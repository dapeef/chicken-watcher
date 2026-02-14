from django.contrib import admin

from .models import (
    Chicken,
    NestingBox,
    Egg,
    NestingBoxPresence,
    NestingBoxImage,
    HardwareSensor,
    NestingBoxPresencePeriod,
)

admin.site.register(Chicken)
admin.site.register(NestingBox)
admin.site.register(Egg)
admin.site.register(NestingBoxPresence)
admin.site.register(NestingBoxImage)
admin.site.register(HardwareSensor)
admin.site.register(NestingBoxPresencePeriod)
