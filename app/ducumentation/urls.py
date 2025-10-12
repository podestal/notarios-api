from rest_framework_nested import routers
from . import views
from django.urls import path, re_path
from django.views.decorators.csrf import csrf_exempt

"""
URL configuration for the Notaria app.
This file defines the URL patterns for the Notaria app.
It includes the URL patterns for the Notaria app's views.
"""

router = routers.DefaultRouter()
router.register('documentos', views.DocumentosGeneradosViewSet)
router.register('extraprotocolares', views.ExtraprotocolaresViewSet, basename='extraprotocolares')
router.register('documentos-logs', views.DocumentosLogsViewSet, basename='documentos-logs')
from .views import download_docx

print("DEBUG: urls.py loaded")

urlpatterns = [
    path('upload-docx/', views.generate_document_by_tipkar, name='generate_document_by_tipkar'),
    path('update-docx/', views.update_document_by_tipkar, name='update_document_by_tipkar'),
    path('save-doc/', csrf_exempt(views.save_doc), name='save_doc'),
    path('generate-token/', views.generate_token, name='generate_token'),
    path('test-r2/', views.test_r2_connection, name='test_r2_connection'),
    re_path(r'^download/(?P<kardex>[^/]+)/__PROY__(?P<kardex2>[^/]+)\.docx$', download_docx, name='download_docx'),
] + router.urls