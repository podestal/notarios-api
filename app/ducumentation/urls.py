from rest_framework_nested import routers
from . import views

"""
URL configuration for the Notaria app.
This file defines the URL patterns for the Notaria app.
It includes the URL patterns for the Notaria app's views.
"""

router = routers.DefaultRouter()

router.register('templates', views.TemplateViewSet)
router.register('documentos', views.DocumentosGeneradosViewSet)

urlpatterns = router.urls