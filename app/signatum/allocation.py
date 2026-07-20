"""
Locked correlative allocation for escrituración reservations.

``CorrelativeCounter`` is the source of truth for the next num_escritura.
Folio advances from ``last_folio`` only after a successful commit so an
expired reservation can reuse the same folio slot.

``num_minuta`` is never allocated here — clerks enter it manually on the kardex.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError

from signatum import correlatives, models


@dataclass(frozen=True)
class AllocatedCorrelatives:
    num_escritura: str
    folio: str


def _parse_positive_int(value: str | None) -> int:
    s = (value or "").strip()
    if not s:
        return 0
    try:
        return max(0, int(s))
    except ValueError:
        return 0


def _seed_defaults_from_history(*, year: int, idtipkar: int) -> dict:
    """Bootstrap counter from the latest committed notarization for year+tipo."""
    last = (
        models.Notarization.objects.filter(
            created_at__year=year,
            idtipkar=idtipkar,
        )
        .order_by("-id")
        .first()
    )
    if last is None:
        return {
            "next_num_escritura": 1,
            "next_num_minuta": 1,
            "last_folio": "",
        }
    return {
        "next_num_escritura": max(1, _parse_positive_int(last.num_escritura) + 1),
        "next_num_minuta": max(1, _parse_positive_int(last.num_minuta) + 1),
        "last_folio": (last.folio_fin or last.folio_ini or "").strip(),
    }


def get_locked_counter(*, year: int, idtipkar: int) -> models.CorrelativeCounter:
    """
    Return the counter row locked for update, creating/seeding it if needed.
    Must run inside ``transaction.atomic``.
    """
    qs = models.CorrelativeCounter.objects.select_for_update()
    counter = qs.filter(year=year, idtipkar=idtipkar).first()
    if counter is not None:
        return counter

    defaults = _seed_defaults_from_history(year=year, idtipkar=idtipkar)
    try:
        models.CorrelativeCounter.objects.create(
            year=year,
            idtipkar=idtipkar,
            **defaults,
        )
    except IntegrityError:
        pass

    counter = qs.filter(year=year, idtipkar=idtipkar).first()
    if counter is None:
        raise RuntimeError(
            f"Could not create correlative counter for year={year} idtipkar={idtipkar}"
        )
    return counter


def allocate_correlatives(*, year: int, idtipkar: int) -> AllocatedCorrelatives:
    """
    Assign the next escritura/folio under a row lock and advance the escritura
    counter. Does not advance ``last_folio`` (commit does).

    Does not allocate ``num_minuta`` — that field is clerk-entered only.
    """
    counter = get_locked_counter(year=year, idtipkar=idtipkar)

    num_escritura = str(counter.next_num_escritura)
    folio = (
        correlatives.bump_folio_papel_string(counter.last_folio)
        if (counter.last_folio or "").strip()
        else "1"
    )

    counter.next_num_escritura = counter.next_num_escritura + 1
    counter.save(update_fields=["next_num_escritura", "updated_at"])

    return AllocatedCorrelatives(
        num_escritura=num_escritura,
        folio=folio,
    )


def advance_folio_on_commit(*, year: int, idtipkar: int, folio_fin: str) -> None:
    """Persist the committed folio_fin so the next reserve bumps from it."""
    folio = (folio_fin or "").strip()
    if not folio:
        return
    counter = get_locked_counter(year=year, idtipkar=idtipkar)
    counter.last_folio = folio
    counter.save(update_fields=["last_folio", "updated_at"])
