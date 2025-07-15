from rest_framework_nested import routers
from . import views
from django.urls import path
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

urlpatterns = [
    path('upload-docx/', views.upload_document_to_r2, name='upload_document_to_r2'),
    path('update-docx/', views.update_document_in_r2, name='update_document_in_r2'),
    path('download/<str:kardex>/<str:filename>/', download_docx, name='download_docx'),
] + router.urls