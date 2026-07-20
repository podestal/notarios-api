from django.urls import include, path
from rest_framework_nested import routers

from . import admin_views, views

"""
URL configuration for the Signatum app.
"""

router = routers.DefaultRouter()
router.register("notarizations", views.NotarizationViewSet, basename="notarizations")
router.register(
    "notarization-reservations",
    views.NotarizationReservationViewSet,
    basename="notarization-reservations",
)
router.register("series-notariales", views.SerieNotarialViewSet, basename="series-notariales")

admin_router = routers.DefaultRouter()
admin_router.register(
    "reservations",
    admin_views.AdminReservationViewSet,
    basename="admin-reservations",
)
admin_router.register(
    "counters",
    admin_views.AdminCorrelativeCounterViewSet,
    basename="admin-counters",
)
admin_router.register(
    "notarizations",
    admin_views.AdminNotarizationViewSet,
    basename="admin-notarizations",
)

urlpatterns = [
    path("", include(router.urls)),
    path("admin/", include(admin_router.urls)),
]
