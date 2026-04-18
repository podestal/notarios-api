from rest_framework_nested import routers
from . import views

"""
URL configuration for the Signatum app.
This file defines the URL patterns for the Signatum app.
It includes the URL patterns for the Signatum app's views.
"""

router = routers.DefaultRouter()
router.register('notarizations', views.NotarizationViewSet, basename='notarizations')
router.register('notarization-reservations', views.NotarizationReservationViewSet, basename='notarization-reservations')

urlpatterns = router.urls