from rest_framework_nested import routers
from . import views
from django.urls import path, re_path
from rest_framework.decorators import api_view
from rest_framework.permissions import IsAuthenticated

"""
URL configuration for the Notaria app.
This file defines the URL patterns for the Notaria app.
It includes the URL patterns for the Notaria app's views.
"""

router = routers.DefaultRouter()
router.register('documentos', views.DocumentosGeneradosViewSet)

from .views import download_docx

print("DEBUG: urls.py loaded")

urlpatterns = [
    path('upload-docx/', views.generate_document_by_tipkar, name='generate_document_by_tipkar'),
    path('update-docx/', views.update_document_by_tipkar, name='update_document_by_tipkar'),
    path('test-r2/', views.test_r2_connection, name='test_r2_connection'),
    re_path(r'^download/(?P<kardex>[^/]+)/__PROY__(?P<kardex2>[^/]+)\.docx$', download_docx, name='download_docx'),
] + router.urls