from django.contrib import admin

from compliance.models import KardexComplianceCache


@admin.register(KardexComplianceCache)
class KardexComplianceCacheAdmin(admin.ModelAdmin):
    list_display = (
        "kardex",
        "idtipkar",
        "fechaescritura",
        "has_errors",
        "uif_error_count",
        "sisgen_error_count",
        "updated_at",
    )
    list_filter = ("has_errors", "idtipkar")
    search_fields = ("kardex", "idkardex")
    readonly_fields = ("created_at", "updated_at")
