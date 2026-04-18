"""
Notarization side-effects kept out of notaria viewsets.

Call :func:`finalize_notarization_from_reservation` after a Kardex PATCH succeeds
when the client sends ``signatum_reservation_id`` (body or query), or expose a
dedicated Signatum endpoint instead if you prefer not to touch Kardex at all.
"""

from __future__ import annotations

from rest_framework.exceptions import ValidationError

from app.notaria.models import Kardex
from app.signatum.models import Notarization, NotarizationReservation


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
    """
    if not user.is_authenticated:
        raise ValidationError("Authentication required to finalize notarization.")

    try:
        reservation = NotarizationReservation.objects.get(pk=reservation_id)
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

    payload = _snapshot_from_kardex(kardex_instance)
    notarization = Notarization.objects.create(
        created_by=user,
        source_reservation=reservation,
        **payload,
    )
    reservation.status = NotarizationReservation.Status.COMMITTED
    reservation.save(update_fields=["status"])
    return notarization
