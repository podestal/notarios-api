from django.contrib import admin

from .models import SisgenSoapResponse, SisgenValidationCache


@admin.register(SisgenValidationCache)
class SisgenValidationCacheAdmin(admin.ModelAdmin):
    list_display = ("kardex", "idkardex", "updated_at", "updated_by")
    search_fields = ("kardex", "idkardex")


@admin.register(SisgenSoapResponse)
class SisgenSoapResponseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "created_at",
        "kardex",
        "document_status",
        "soap_return_status",
        "http_status",
        "batch_index",
    )
    list_filter = ("document_status", "soap_return_status")
    search_fields = ("kardex", "idkardex", "soap_return_message")
    readonly_fields = ("created_at", "parsed_payload", "raw_response_xml")
