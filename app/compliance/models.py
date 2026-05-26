from django.conf import settings
from django.db import models


class KardexComplianceCache(models.Model):
    """
    Option B — one JSON snapshot per kardex (UIF + SISGEN; PDT reserved).

    Denormalized counters support filters without JSON queries.
    """

    kardex = models.CharField(max_length=32, unique=True, db_index=True)
    idkardex = models.CharField(max_length=32, blank=True, default="", db_index=True)
    idtipkar = models.IntegerField(null=True, blank=True, db_index=True)
    fechaescritura = models.DateField(null=True, blank=True, db_index=True)

    payload = models.JSONField(default=dict)

    uif_error_count = models.PositiveIntegerField(default=0)
    sisgen_error_count = models.PositiveIntegerField(default=0)
    sisgen_observation_count = models.PositiveIntegerField(default=0)
    total_error_count = models.PositiveIntegerField(default=0)
    has_errors = models.BooleanField(default=False, db_index=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="compliance_cache_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["fechaescritura", "has_errors"]),
            models.Index(fields=["idtipkar", "has_errors"]),
        ]

    def __str__(self) -> str:
        return f"{self.kardex} errors={self.total_error_count}"
