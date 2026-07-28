"""
Notarization side-effects kept out of notaria viewsets.

Call :func:`finalize_notarization_from_reservation` after a Kardex PATCH succeeds
when the client sends ``signatum_reservation_id`` (body or query).

Call :func:`reverse_committed_for_kardex` when a Kardex PATCH clears escrituración.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError

from notaria.models import Kardex
from signatum import allocation, correlatives
from signatum.models import Notarization, NotarizationReservation

# Fields the UI sends when saving / clearing escrituración on kardex PATCH.
ESCRITURACION_FIELDS = (
    "numescritura",
    "fechaescritura",
    "folioini",
    "foliofin",
    "papelini",
    "papelfin",
    "numminuta",
    "fechaconclusion",
)


def _norm(value) -> str:
    return str(value or "").strip()


def _norm_folio(value) -> str:
    return _norm(value).upper()


def _is_blank(value) -> bool:
    return not _norm(value)


def is_clearing_escrituracion(instance: Kardex, data) -> bool:
    """
    True when PATCH is wiping escrituración that was previously recorded.

    Distinguishes from a normal escrituración update (non-empty correlatives)
    and from unrelated kardex patches that omit these fields.
    """
    if not isinstance(data, dict):
        return False
    if _is_blank(getattr(instance, "numescritura", None)):
        return False
    if "numescritura" not in data:
        return False
    if not _is_blank(data.get("numescritura")):
        return False
    # Require that the payload is actually touching escrituración (not only
    # blanking numescritura by accident while sending other fields).
    touched = [f for f in ESCRITURACION_FIELDS if f in data]
    if len(touched) < 2:
        return False
    return True


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

    if not _norm(kardex_instance.foliofin):
        reserved_folio_fin = _norm(reservation.folio_fin) or reserved_folio_ini
        if reserved_folio_fin:
            kardex_instance.foliofin = reserved_folio_fin
            updated.append("foliofin")

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
    reservation committed.
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


def _clear_kardex_escrituracion_if_matches(notarization: Notarization) -> dict:
    kardex_row = Kardex.objects.filter(kardex=notarization.kardex).first()
    if kardex_row is None:
        return {"kardex": notarization.kardex, "cleared": False, "reason": "not_found"}

    esc = _norm(notarization.num_escritura)
    current = _norm(kardex_row.numescritura)
    if esc and current and current != esc:
        return {
            "kardex": notarization.kardex,
            "cleared": False,
            "reason": "numescritura_mismatch",
            "kardex_numescritura": current,
            "notarization_num_escritura": esc,
        }

    fields = list(ESCRITURACION_FIELDS)
    for name in fields:
        setattr(kardex_row, name, "")
    kardex_row.save(update_fields=fields)
    return {
        "kardex": notarization.kardex,
        "cleared": True,
        "updated_fields": fields,
    }


def reverse_committed_reservation(
    *,
    reservation: NotarizationReservation,
    clear_kardex: bool = True,
    hard_delete: bool = False,
    reason: str = "",
    user=None,
) -> dict:
    """
    Undo a committed reservation: delete notarization, rebuild counter,
    optionally clear kardex / delete reservation row.

    Caller should hold ``transaction.atomic`` and preferably
    ``select_for_update`` on the reservation.
    """
    if reservation.status != NotarizationReservation.Status.COMMITTED:
        raise ValidationError(
            {
                "status": (
                    "Only committed (CO) reservations can be reversed; "
                    f"current status is {reservation.status}."
                )
            }
        )

    notarization = (
        Notarization.objects.select_for_update()
        .filter(source_reservation_id=reservation.id)
        .first()
    )
    if notarization is None:
        qs = Notarization.objects.select_for_update().filter(
            kardex=reservation.kardex,
            idtipkar=reservation.idtipkar,
        )
        if _norm(reservation.num_escritura):
            qs = qs.filter(num_escritura=_norm(reservation.num_escritura))
        notarization = qs.order_by("-id").first()

    notarization_snapshot = None
    year = correlatives.correlative_year_today()
    if notarization is not None:
        year = notarization.created_at.year if notarization.created_at else year
        notarization_snapshot = {
            "id": notarization.id,
            "kardex": notarization.kardex,
            "num_escritura": notarization.num_escritura,
            "folio_ini": notarization.folio_ini,
            "folio_fin": notarization.folio_fin,
            "papel_ini": notarization.papel_ini,
            "papel_fin": notarization.papel_fin,
            "fecha_escritura": notarization.fecha_escritura,
        }

    kardex_cleared = None
    if clear_kardex and notarization is not None:
        kardex_cleared = _clear_kardex_escrituracion_if_matches(notarization)

    freed_num = None
    freed_folio = None
    if notarization_snapshot is not None:
        freed_num = notarization_snapshot.get("num_escritura")
        freed_folio = (
            notarization_snapshot.get("folio_ini")
            or notarization_snapshot.get("folio_fin")
        )
    if not freed_num:
        freed_num = reservation.num_escritura
    if not freed_folio:
        freed_folio = reservation.folio_ini or reservation.folio_fin

    if notarization is not None:
        notarization.delete()

    counter = allocation.rebuild_counter_from_history(
        year=year,
        idtipkar=reservation.idtipkar,
        freed_num_escritura=freed_num,
        freed_folio=freed_folio,
    )
    counter_snapshot = {
        "id": counter.id,
        "year": counter.year,
        "idtipkar": counter.idtipkar,
        "next_num_escritura": counter.next_num_escritura,
        "last_folio": counter.last_folio,
        "freed_num_escrituras": list(counter.freed_num_escrituras or []),
    }

    reservation_id = reservation.id
    kardex_code = reservation.kardex
    if hard_delete:
        reservation.delete()
        reservation_payload = {
            "id": reservation_id,
            "status": "deleted",
            "kardex": kardex_code,
        }
    else:
        reservation.status = NotarizationReservation.Status.REVERSED
        reservation.save(update_fields=["status"])
        reservation_payload = {
            "id": reservation.id,
            "status": reservation.status,
            "kardex": reservation.kardex,
            "num_escritura": reservation.num_escritura,
            "idtipkar": reservation.idtipkar,
        }

    return {
        "reservation": reservation_payload,
        "deleted_notarization": notarization_snapshot,
        "kardex_cleared": kardex_cleared,
        "counter": counter_snapshot,
        "hard_delete": hard_delete,
        "reason": reason,
        "by_user_id": getattr(user, "id", None),
    }


def reverse_committed_for_kardex(
    *,
    kardex_code: str,
    idtipkar: int,
    num_escritura: str | None = None,
    clear_kardex: bool = False,
    reason: str = "",
    user=None,
) -> dict | None:
    """
    Free correlatives when kardex escrituración is cleared.

    Finds the committed reservation (and notarization) for this kardex and
    reverses it. ``clear_kardex`` defaults to False because the kardex PATCH
    usually already wiped the fields.
    """
    code = _norm(kardex_code)
    if not code:
        return None

    with transaction.atomic():
        reservation = (
            NotarizationReservation.objects.select_for_update()
            .filter(
                kardex=code,
                idtipkar=idtipkar,
                status=NotarizationReservation.Status.COMMITTED,
            )
            .order_by("-id")
            .first()
        )

        if reservation is None:
            notarization = (
                Notarization.objects.select_for_update()
                .filter(kardex=code, idtipkar=idtipkar)
                .order_by("-id")
                .first()
            )
            if notarization is None:
                return None
            if num_escritura and _norm(notarization.num_escritura) != _norm(num_escritura):
                notarization = (
                    Notarization.objects.select_for_update()
                    .filter(
                        kardex=code,
                        idtipkar=idtipkar,
                        num_escritura=_norm(num_escritura),
                    )
                    .order_by("-id")
                    .first()
                )
            if notarization is None:
                return None

            year = (
                notarization.created_at.year
                if notarization.created_at
                else correlatives.correlative_year_today()
            )
            snapshot = {
                "id": notarization.id,
                "kardex": notarization.kardex,
                "num_escritura": notarization.num_escritura,
                "folio_ini": notarization.folio_ini,
                "folio_fin": notarization.folio_fin,
            }
            tipkar = notarization.idtipkar
            freed_num = snapshot.get("num_escritura")
            freed_folio = snapshot.get("folio_ini") or snapshot.get("folio_fin")
            if clear_kardex:
                _clear_kardex_escrituracion_if_matches(notarization)
            notarization.delete()
            counter = allocation.rebuild_counter_from_history(
                year=year,
                idtipkar=tipkar,
                freed_num_escritura=freed_num,
                freed_folio=freed_folio,
            )
            return {
                "reservation": None,
                "deleted_notarization": snapshot,
                "kardex_cleared": {"cleared": clear_kardex},
                "counter": {
                    "next_num_escritura": counter.next_num_escritura,
                    "last_folio": counter.last_folio,
                    "freed_num_escrituras": list(counter.freed_num_escrituras or []),
                    "year": counter.year,
                    "idtipkar": counter.idtipkar,
                },
                "reason": reason,
                "by_user_id": getattr(user, "id", None),
            }

        if num_escritura and _norm(reservation.num_escritura) not in (
            "",
            _norm(num_escritura),
        ):
            matched = (
                NotarizationReservation.objects.select_for_update()
                .filter(
                    kardex=code,
                    idtipkar=idtipkar,
                    status=NotarizationReservation.Status.COMMITTED,
                    num_escritura=_norm(num_escritura),
                )
                .order_by("-id")
                .first()
            )
            if matched is not None:
                reservation = matched

        return reverse_committed_reservation(
            reservation=reservation,
            clear_kardex=clear_kardex,
            hard_delete=False,
            reason=reason or "Kardex escrituración cleared",
            user=user,
        )
