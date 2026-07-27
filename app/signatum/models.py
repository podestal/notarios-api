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
        REVERSED = "RV", "Reversed"

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


class SerieNotarial(models.Model):
    """
    Purchased notarial paper ranges used to propose papel_ini/papel_fin.
    Ranges are not globally correlative; they are consumed within each purchased
    range and can jump when a new range is added.
    """

    idtipkar = models.IntegerField(
        default=1,
        help_text="Tipo de kardex this series applies to.",
    )
    nombre = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional label for the purchased range/lot.",
    )
    papel_ini = models.CharField(max_length=30)
    papel_fin = models.CharField(max_length=30)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("created_at", "id")


class CorrelativeCounter(models.Model):
    """
    Authoritative next correlatives per calendar year + tipo de kardex.

    Allocation locks this row with SELECT FOR UPDATE so concurrent reserves
    cannot hand out the same num_escritura. last_folio advances only on commit
    so an expired reservation can reuse the same folio slot.
    """

    year = models.PositiveIntegerField()
    idtipkar = models.IntegerField()
    next_num_escritura = models.PositiveIntegerField(default=1)
    next_num_minuta = models.PositiveIntegerField(default=1)
    last_folio = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Last committed folio_fin; next reserve bumps from this.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-year", "idtipkar")
        constraints = [
            models.UniqueConstraint(
                fields=("year", "idtipkar"),
                name="signatum_correlative_counter_year_idtipkar_uniq",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Counter y={self.year} tipkar={self.idtipkar} "
            f"next_esc={self.next_num_escritura} folio={self.last_folio!r}"
        )
