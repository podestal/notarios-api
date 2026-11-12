from django.conf import settings
from django.db import models


class DocumentoBien(models.Model):
    """
    Uploaded SUNARP (or similar) PDF linked to its parsed JSON payload.

    ``tipo`` starts as ``vehicular``; ``inmueble`` comes later.
    """

    TIPO_VEHICULAR = "vehicular"
    TIPO_INMUEBLE = "inmueble"
    TIPO_CHOICES = (
        (TIPO_VEHICULAR, "Vehicular"),
        (TIPO_INMUEBLE, "Inmueble"),
    )

    STATUS_PENDING = "pending"
    STATUS_PARSED = "parsed"
    STATUS_APPLIED = "applied"
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_PARSED, "Parsed"),
        (STATUS_APPLIED, "Applied"),
        (STATUS_ERROR, "Error"),
    )

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    original_filename = models.CharField(max_length=255)
    stored_filename = models.CharField(max_length=255)
    relative_path = models.CharField(max_length=512)
    content_type = models.CharField(max_length=100, blank=True, default="application/pdf")
    file_size = models.PositiveIntegerField(default=0)

    # Denormalized keys for lookup (vehicular first).
    placa = models.CharField(max_length=32, blank=True, default="", db_index=True)
    partida = models.CharField(max_length=64, blank=True, default="", db_index=True)
    oficina = models.CharField(max_length=128, blank=True, default="")

    raw_text = models.TextField(blank=True, default="")
    parsed = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    parse_error = models.TextField(blank=True, default="")

    # Linked detallevehicular once the user selects this parsed boleta.
    detveh = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    kardex = models.CharField(max_length=30, blank=True, default="", db_index=True)
    idtipacto = models.CharField(max_length=20, blank=True, default="")
    applied_at = models.DateTimeField(null=True, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documentos_bien_uploads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tipo", "placa"]),
            models.Index(fields=["tipo", "status"]),
            models.Index(fields=["tipo", "status", "detveh"]),
        ]

    def __str__(self) -> str:
        return f"{self.tipo}:{self.placa or self.stored_filename} ({self.status})"
