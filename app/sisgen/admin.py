from django.contrib import admin

from .models import (
    SisgenSendJob,
    SisgenSendJobDocument,
    SisgenSoapResponse,
    SisgenValidationCache,
)


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


class SisgenSendJobDocumentInline(admin.TabularInline):
    model = SisgenSendJobDocument
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "kardex",
        "idkardex",
        "status",
        "batch_index",
        "attempt",
        "message",
        "submission_response",
    )


@admin.register(SisgenSendJob)
class SisgenSendJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "user",
        "progress_processed",
        "progress_total",
        "celery_task_id",
        "created_at",
        "finished_at",
    )
    list_filter = ("status",)
    search_fields = ("celery_task_id", "user__username")
    readonly_fields = ("created_at", "updated_at", "finished_at", "payload", "result")
    inlines = [SisgenSendJobDocumentInline]
