from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("partials/eggs-today/", views.partial_eggs_today, name="partial_eggs_today"),
    path("partials/laid-chickens/", views.partial_laid_chickens, name="partial_laid_chickens"),
    path("partials/sensors/", views.partial_sensors, name="partial_sensors"),
    path("partials/latest-image/", views.partial_latest_image, name="partial_latest_image"),
    path("partials/latest-presence/", views.partial_latest_presence, name="partial_latest_presence"),
    path("partials/latest-events/", views.partial_latest_events, name="partial_latest_events"),
    path("chickens/", views.ChickenListView.as_view(), name="chicken_list"),
    path(
        "chickens/<int:pk>/", views.ChickenDetailView.as_view(), name="chicken_detail"
    ),
    path("eggs/", views.EggListView.as_view(), name="egg_list"),
    path("eggs/new/", views.EggCreateView.as_view(), name="egg_create"),
    path("analytics/eggs/", views.EggProductionView.as_view(), name="egg_production"),
]
