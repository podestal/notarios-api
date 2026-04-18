from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def _default_reservation_expires():
    return timezone.now() + timedelta(minutes=5)


class Notarization(models.Model):
    """Persisted escrituración correlatives; `kardex` is the legacy kardex code string."""

    kardex = models.CharField(max_length=30)
    fecha_conclusion = models.CharField(max_length=10, blank=True)
    folio_ini = models.CharField(max_length=30, blank=True)
    folio_fin = models.CharField(max_length=30, blank=True)
    papel_ini = models.CharField(max_length=30, blank=True)
    papel_fin = models.CharField(max_length=30, blank=True)
    num_minuta = models.CharField(max_length=100, blank=True)
    num_escritura = models.CharField(max_length=100, blank=True)
    fecha_escritura = models.CharField(max_length=10, blank=True)

    source_reservation = models.OneToOneField(
        "NotarizationReservation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="committed_notarization",
        help_text="Reservation that produced this row, if any.",
    )

    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signatum_notarizations_created",
    )

    class Meta:
        ordering = ("-id",)

class NotarizationReservation(models.Model):
    """Draft correlatives; `status=PE` and `expires_at` in the future means locked for others."""

    class Status(models.TextChoices):
        PENDING = "PE", "Pending"
        COMMITTED = "CO", "Committed"
        CANCELLED = "CA", "Cancelled"
        EXPIRED = "EX", "Expired"

    kardex = models.CharField(max_length=30)
    fecha_conclusion = models.CharField(max_length=10, blank=True)
    folio_ini = models.CharField(max_length=30, blank=True)
    folio_fin = models.CharField(max_length=30, blank=True)
    papel_ini = models.CharField(max_length=30, blank=True)
    papel_fin = models.CharField(max_length=30, blank=True)
    num_minuta = models.CharField(max_length=100, blank=True)
    num_escritura = models.CharField(max_length=100, blank=True)
    fecha_escritura = models.CharField(max_length=10, blank=True)

    status = models.CharField(
        max_length=2,
        choices=Status.choices,
        default=Status.PENDING,
    )
    held_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signatum_notarization_reservations",
    )
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(default=_default_reservation_expires)

    class Meta:
        ordering = ("-id",)
