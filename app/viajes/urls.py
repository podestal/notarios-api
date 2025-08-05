from django.urls import path, include
from rest_framework import routers
from .views import ViajeViewSet, ParticipanteViewSet

router = routers.DefaultRouter()

router.register('viajes', ViajeViewSet, basename='viajes')
router.register('participantes', ParticipanteViewSet, basename='participantes')

urlpatterns = router.urls