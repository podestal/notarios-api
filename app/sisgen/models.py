from django.conf import settings
from django.db import models


class SisgenValidationCache(models.Model):
    kardex = models.CharField(max_length=32, unique=True, db_index=True)
    idkardex = models.CharField(max_length=32, blank=True, default="")
    payload = models.JSONField(default=dict)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sisgen_validation_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.kardex} ({self.updated_at:%Y-%m-%d %H:%M:%S})"
