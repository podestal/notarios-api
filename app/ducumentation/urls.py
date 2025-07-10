from rest_framework_nested import routers
from . import views
from django.urls import path

"""
URL configuration for the Notaria app.
This file defines the URL patterns for the Notaria app.
It includes the URL patterns for the Notaria app's views.
"""

router = routers.DefaultRouter()
router.register('documentos', views.DocumentosGeneradosViewSet)

urlpatterns = router.urls + [
    path('upload-docx/', views.upload_document_to_r2, name='upload_document_to_r2'),
]