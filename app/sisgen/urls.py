# sisgen_service/urls.py
from django.urls import path
from .views import (
    DocumentSearchView,
    SendToSISGENPreviewView,
    SendToSISGENView,
    SisgenErrorsByKardexView,
    SisgenSendJobDetailView,
    SisgenSoapResponseListView,
    SisgenValidationRecalculateView,
)

app_name = 'sisgen_service'

urlpatterns = [
    path('search/', DocumentSearchView.as_view(), name='document_search'),
    path(
        'errors/kardex/<str:kardex>/',
        SisgenErrorsByKardexView.as_view(),
        name='sisgen_errors_by_kardex',
    ),
    path(
        'send-sisgen/preview/',
        SendToSISGENPreviewView.as_view(),
        name='send_sisgen_preview',
    ),
    path('send-sisgen/', SendToSISGENView.as_view(), name='send_sisgen'),
    path(
        'send-jobs/<int:job_id>/',
        SisgenSendJobDetailView.as_view(),
        name='send_job_detail',
    ),
    path(
        'submission-responses/',
        SisgenSoapResponseListView.as_view(),
        name='sisgen_submission_responses_list',
    ),
    path(
        'submission-responses/kardex/<str:kardex>/',
        SisgenSoapResponseListView.as_view(),
        name='sisgen_submission_responses_by_kardex',
    ),
    path(
        'validation/recalculate/',
        SisgenValidationRecalculateView.as_view(),
        name='validation_recalculate',
    ),
]