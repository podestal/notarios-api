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


class SisgenSendJob(models.Model):
    """Async SISGEN send job — source of truth for UI polling."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sisgen_send_jobs",
    )
    celery_task_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payload = models.JSONField(default=dict)
    progress_processed = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"SisgenSendJob #{self.pk} ({self.status})"

    @property
    def progress_label(self) -> str:
        return f"{self.progress_processed}/{self.progress_total}"


class SisgenSendJobDocument(models.Model):
    """Per-kardex row within a send job."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    class Attempt(models.TextChoices):
        BATCH = "batch", "Batch"
        SINGLE = "single", "Single"

    job = models.ForeignKey(
        SisgenSendJob,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    kardex = models.CharField(max_length=32, db_index=True)
    idkardex = models.CharField(max_length=32, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    batch_index = models.PositiveSmallIntegerField(default=0)
    attempt = models.CharField(
        max_length=16,
        choices=Attempt.choices,
        blank=True,
        default="",
    )
    message = models.TextField(blank=True, default="")
    submission_response = models.ForeignKey(
        SisgenSoapResponse,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="send_job_documents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "kardex"],
                name="sisgen_send_job_document_unique_kardex",
            ),
        ]
        indexes = [
            models.Index(fields=["job", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.kardex} ({self.status})"
