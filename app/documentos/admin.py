from django.contrib import admin

from documentos.models import DocumentoBien


@admin.register(DocumentoBien)
class DocumentoBienAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tipo",
        "placa",
        "partida",
        "status",
        "original_filename",
        "created_at",
    )
    list_filter = ("tipo", "status")
    search_fields = ("placa", "partida", "original_filename", "stored_filename")
