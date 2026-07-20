"""
Locked correlative allocation for escrituración reservations.

``CorrelativeCounter`` is the source of truth for the next num_escritura.
Folio advances from ``last_folio`` only after a successful commit so an
expired reservation can reuse the same folio slot. num_minuta follows
legacy bump-from-last-notarization behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError

from signatum import correlatives, models


@dataclass(frozen=True)
class AllocatedCorrelatives:
    num_escritura: str
    num_minuta: str
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

    ``num_minuta`` follows legacy behavior: bump from the last committed
    notarization for the year (empty history -> \"1\"), so actos that leave
    minuta blank keep receiving \"1\" instead of drifting 1,2,3...
    """
    counter = get_locked_counter(year=year, idtipkar=idtipkar)

    num_escritura = str(counter.next_num_escritura)
    folio = (
        correlatives.bump_folio_papel_string(counter.last_folio)
        if (counter.last_folio or "").strip()
        else "1"
    )

    last = (
        models.Notarization.objects.filter(
            created_at__year=year,
            idtipkar=idtipkar,
        )
        .order_by("-id")
        .first()
    )
    num_minuta = correlatives.bump_int_string(last.num_minuta if last else "")

    counter.next_num_escritura = counter.next_num_escritura + 1
    # Keep next_num_minuta in sync for future admin tooling, but do not use it
    # as the allocator while legacy empty-minuta behavior is required.
    try:
        counter.next_num_minuta = max(1, int(num_minuta) + 1)
    except ValueError:
        counter.next_num_minuta = 1
    counter.save(
        update_fields=["next_num_escritura", "next_num_minuta", "updated_at"]
    )

    return AllocatedCorrelatives(
        num_escritura=num_escritura,
        num_minuta=num_minuta,
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
