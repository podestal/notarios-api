# sisgen_service/urls.py
from django.urls import path
from .views import (
    DocumentSearchView,
    SendToSISGENView,
    SisgenValidationRecalculateView,
)

app_name = 'sisgen_service'

urlpatterns = [
    path('search/', DocumentSearchView.as_view(), name='document_search'),
    path('send-sisgen/', SendToSISGENView.as_view(), name='send_sisgen'),
    path(
        'validation/recalculate/',
        SisgenValidationRecalculateView.as_view(),
        name='validation_recalculate',
    ),
]