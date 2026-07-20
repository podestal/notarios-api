"""
Notarization side-effects kept out of notaria viewsets.

Call :func:`finalize_notarization_from_reservation` after a Kardex PATCH succeeds
when the client sends ``signatum_reservation_id`` (body or query), or expose a
dedicated Signatum endpoint instead if you prefer not to touch Kardex at all.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError

from notaria.models import Kardex
from signatum import allocation, correlatives
from signatum.models import Notarization, NotarizationReservation


def _norm(value) -> str:
    return str(value or "").strip()


def _norm_folio(value) -> str:
    return _norm(value).upper()


def _snapshot_from_kardex(k: Kardex) -> dict:
    code = (k.kardex or "").strip()
    if not code:
        raise ValidationError({"kardex": "Kardex code is empty; cannot record notarization."})
    return {
        "idtipkar": k.idtipkar,
        "kardex": code,
        "fecha_conclusion": k.fechaconclusion or "",
        "folio_ini": k.folioini or "",
        "folio_fin": k.foliofin or "",
        "papel_ini": k.papelini or "",
        "papel_fin": k.papelfin or "",
        "num_minuta": k.numminuta or "",
        "num_escritura": k.numescritura or "",
        "fecha_escritura": k.fechaescritura or "",
    }


def _apply_reservation_to_kardex(
    kardex_instance: Kardex,
    reservation: NotarizationReservation,
) -> list[str]:
    """
    Force authoritative reserved correlatives onto the kardex row.

    Client may still send stale numescritura/folioini; reservation wins.
    folio_fin / papel_* may be widened by the client (multi-page acts).
    num_minuta is never applied from the reservation (clerk-entered).
    """
    updated: list[str] = []

    reserved_esc = _norm(reservation.num_escritura)
    if reserved_esc and _norm(kardex_instance.numescritura) != reserved_esc:
        kardex_instance.numescritura = reserved_esc
        updated.append("numescritura")

    reserved_folio_ini = _norm(reservation.folio_ini)
    if reserved_folio_ini and _norm(kardex_instance.folioini) != reserved_folio_ini:
        kardex_instance.folioini = reserved_folio_ini
        updated.append("folioini")

    # folio_fin: keep client value if set; otherwise use reservation.
    if not _norm(kardex_instance.foliofin):
        reserved_folio_fin = _norm(reservation.folio_fin) or reserved_folio_ini
        if reserved_folio_fin:
            kardex_instance.foliofin = reserved_folio_fin
            updated.append("foliofin")

    # num_minuta is clerk-entered on kardex; never overwrite from reservation.

    reserved_fecha = _norm(reservation.fecha_escritura)
    if reserved_fecha and not _norm(kardex_instance.fechaescritura):
        kardex_instance.fechaescritura = reserved_fecha
        updated.append("fechaescritura")

    if _norm(reservation.papel_ini) and not _norm(kardex_instance.papelini):
        kardex_instance.papelini = reservation.papel_ini
        updated.append("papelini")
    if _norm(reservation.papel_fin) and not _norm(kardex_instance.papelfin):
        kardex_instance.papelfin = reservation.papel_fin
        updated.append("papelfin")

    if updated:
        kardex_instance.save(update_fields=updated)
    return updated


def finalize_notarization_from_reservation(
    *,
    kardex_instance: Kardex,
    reservation_id: int,
    user,
) -> Notarization:
    """
    Create ``Notarization`` from the saved Kardex correlatives and mark the
    reservation committed. Caller should run inside the same ``transaction.atomic``
    as the Kardex save so validation failures roll back the Kardex update.

    Reserved ``num_escritura`` / ``folio_ini`` always win over client payload so
    stale UI values cannot duplicate correlatives.
    """
    if not user.is_authenticated:
        raise ValidationError("Authentication required to finalize notarization.")

    with transaction.atomic():
        try:
            reservation = (
                NotarizationReservation.objects.select_for_update().get(pk=reservation_id)
            )
        except NotarizationReservation.DoesNotExist:
            raise ValidationError(
                {"signatum_reservation_id": "Reservation not found."},
            )

        k_code = (kardex_instance.kardex or "").strip()
        if (reservation.kardex or "").strip() != k_code:
            raise ValidationError(
                {"signatum_reservation_id": "Reservation kardex does not match this kardex."},
            )

        if reservation.idtipkar != kardex_instance.idtipkar:
            raise ValidationError(
                {"signatum_reservation_id": "Reservation idtipkar does not match this kardex."},
            )

        if reservation.status != NotarizationReservation.Status.PENDING:
            raise ValidationError(
                {"signatum_reservation_id": "Reservation is not pending."},
            )

        if reservation.held_by_id != user.id:
            raise ValidationError(
                {"signatum_reservation_id": "Reservation belongs to another user."},
            )

        # Hard guard: after apply, snapshot must match reserved escritura + folio_ini.
        _apply_reservation_to_kardex(kardex_instance, reservation)

        if _norm(kardex_instance.numescritura) != _norm(reservation.num_escritura):
            raise ValidationError(
                {
                    "numescritura": (
                        f"Must match reserved number {reservation.num_escritura}."
                    )
                }
            )
        if _norm_folio(kardex_instance.folioini) != _norm_folio(reservation.folio_ini):
            raise ValidationError(
                {
                    "folioini": (
                        f"Must match reserved folio {reservation.folio_ini}."
                    )
                }
            )

        payload = _snapshot_from_kardex(kardex_instance)
        notarization = Notarization.objects.create(
            created_by=user,
            source_reservation=reservation,
            **payload,
        )
        reservation.status = NotarizationReservation.Status.COMMITTED
        reservation.save(update_fields=["status"])

        year = correlatives.correlative_year_today()
        allocation.advance_folio_on_commit(
            year=year,
            idtipkar=reservation.idtipkar,
            folio_fin=payload["folio_fin"] or payload["folio_ini"],
        )

        return notarization
