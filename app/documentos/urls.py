from django.urls import path

from documentos.views import (
    DocumentoBienDetailView,
    DocumentoVehicularApplyView,
    DocumentoVehicularListCreateView,
    DocumentoVehicularPendingView,
)

app_name = "documentos"

urlpatterns = [
    path(
        "vehiculares/",
        DocumentoVehicularListCreateView.as_view(),
        name="vehiculares-list-create",
    ),
    path(
        "vehiculares/pendientes/",
        DocumentoVehicularPendingView.as_view(),
        name="vehiculares-pendientes",
    ),
    path(
        "vehiculares/aplicar/",
        DocumentoVehicularApplyView.as_view(),
        name="vehiculares-aplicar",
    ),
    path("<int:pk>/", DocumentoBienDetailView.as_view(), name="detalle"),
]
