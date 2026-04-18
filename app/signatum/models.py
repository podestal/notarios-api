from django.conf import settings
from django.db import models
from django.utils import timezone


class Notarization(models.Model):
    """Persisted escrituración correlatives; `kardex` is the legacy kardex code string."""

    idtipkar = models.IntegerField(
        help_text="Tipo de kardex; correlatives and locks are scoped per tipo.",
    )
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
    """Draft correlatives; `status=PE` blocks other users for the same idtipkar until released or stale."""

    class Status(models.TextChoices):
        PENDING = "PE", "Pending"
        COMMITTED = "CO", "Committed"
        CANCELLED = "CA", "Cancelled"
        EXPIRED = "EX", "Expired"

    idtipkar = models.IntegerField(
        help_text="Tipo de kardex; pending lock and correlatives are independent per tipo.",
    )
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

    class Meta:
        ordering = ("-id",)
