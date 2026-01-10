from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("chickens/", views.ChickenListView.as_view(), name="chicken_list"),
    path(
        "chickens/<int:pk>/", views.ChickenDetailView.as_view(), name="chicken_detail"
    ),
    path("eggs/", views.EggListView.as_view(), name="egg_list"),
    path("eggs/new/", views.EggCreateView.as_view(), name="egg_create"),
    path("boxes/", views.NestingBoxListView.as_view(), name="box_list"),
    path("analytics/eggs/", views.EggProductionView.as_view(), name="egg_production"),
]
