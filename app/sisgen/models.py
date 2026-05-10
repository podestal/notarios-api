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


class SisgenSoapResponse(models.Model):
    """
    Respuesta HTTP/SOAP de SISGEN tras enviar documentos (para dashboard).

    Una fila por kardex afectado en ese POST (o por cada DocumentoNotarial devuelto).
    El XML crudo y el JSON parseado permiten mostrar estado y errores sin reprocesar SOAP.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    kardex = models.CharField(max_length=32, db_index=True)
    idkardex = models.CharField(max_length=32, blank=True, default="")
    batch_index = models.PositiveSmallIntegerField(default=1)

    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    soap_return_status = models.CharField(max_length=64, blank=True, default="")
    soap_return_message = models.TextField(blank=True, default="")
    document_status = models.CharField(max_length=64, blank=True, default="")

    parsed_payload = models.JSONField(default=dict)
    raw_response_xml = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sisgen_soap_responses",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["kardex", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kardex} @ {self.created_at:%Y-%m-%d %H:%M} ({self.document_status or self.soap_return_status})"
