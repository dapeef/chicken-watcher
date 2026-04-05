from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("partials/eggs-today/", views.partial_eggs_today, name="partial_eggs_today"),
    path(
        "partials/laid-chickens/",
        views.partial_laid_chickens,
        name="partial_laid_chickens",
    ),
    path("partials/sensors/", views.partial_sensors, name="partial_sensors"),
    path(
        "partials/latest-image/",
        views.partial_latest_image,
        name="partial_latest_image",
    ),
    path(
        "partials/latest-presence/",
        views.partial_latest_presence,
        name="partial_latest_presence",
    ),
    path(
        "partials/latest-events/",
        views.partial_latest_events,
        name="partial_latest_events",
    ),
    path("chickens/", views.ChickenListView.as_view(), name="chicken_list"),
    path(
        "chickens/<int:pk>/", views.ChickenDetailView.as_view(), name="chicken_detail"
    ),
    path(
        "chickens/<int:pk>/timeline-data/",
        views.chicken_timeline_data,
        name="chicken_timeline_data",
    ),
    path("eggs/", views.EggListView.as_view(), name="egg_list"),
    path("eggs/new/", views.EggCreateView.as_view(), name="egg_create"),
    path("eggs/<int:pk>/delete/", views.EggDeleteView.as_view(), name="egg_delete"),
    path("metrics/", views.MetricsView.as_view(), name="metrics"),
    path("timeline/", views.TimelineView.as_view(), name="timeline"),
    path("timeline/data/", views.timeline_data, name="timeline_data"),
    path("timeline/images/", views.timeline_images, name="timeline_images"),
    path(
        "partials/image-at-time/",
        views.partial_image_at_time,
        name="partial_image_at_time",
    ),
]
