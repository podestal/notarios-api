"""
Locked correlative allocation for escrituración reservations.

``CorrelativeCounter`` is the source of truth for the next num_escritura.
Folio advances from ``last_folio`` only after a successful commit so an
expired reservation can reuse the same folio slot.

When a committed (or pending) slot is released while higher numbers remain
in use, it goes into ``freed_num_escrituras`` as
``{"num_escritura": 147, "folio": "10"}`` and is handed out again on the
next reserve (lowest escritura first, with its original folio).

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


def _norm_folio(value: str | None) -> str:
    return (value or "").strip().upper()


def _normalize_freed_slots(values) -> list[dict]:
    """
    Normalize freed pool entries to ``{"num_escritura": int, "folio": str}``.

    Accepts legacy ``[147]`` ints and new dict slots.
    """
    by_num: dict[int, str] = {}
    for raw in values or []:
        if isinstance(raw, dict):
            n = _parse_positive_int(str(raw.get("num_escritura", "")))
            folio = (raw.get("folio") or "").strip()
        else:
            n = _parse_positive_int(str(raw))
            folio = ""
        if n < 1:
            continue
        # Keep first folio seen for a number; prefer non-empty.
        if n not in by_num or (folio and not by_num[n]):
            by_num[n] = folio
    return [
        {"num_escritura": n, "folio": by_num[n]}
        for n in sorted(by_num)
    ]


def _notarization_nums(*, year: int, idtipkar: int) -> set[int]:
    nums: set[int] = set()
    for raw in models.Notarization.objects.filter(
        created_at__year=year,
        idtipkar=idtipkar,
    ).values_list("num_escritura", flat=True):
        n = _parse_positive_int(raw)
        if n:
            nums.add(n)
    return nums


def _pending_reservation_nums(*, idtipkar: int) -> set[int]:
    """Numbers currently held by pending reservations for this tipo."""
    nums: set[int] = set()
    for raw in models.NotarizationReservation.objects.filter(
        idtipkar=idtipkar,
        status=models.NotarizationReservation.Status.PENDING,
    ).values_list("num_escritura", flat=True):
        n = _parse_positive_int(raw)
        if n:
            nums.add(n)
    return nums


def _taken_folios(*, year: int, idtipkar: int) -> set[str]:
    """Folio values currently held by notarizations or pending reservations."""
    taken: set[str] = set()
    for folio_ini, folio_fin in models.Notarization.objects.filter(
        created_at__year=year,
        idtipkar=idtipkar,
    ).values_list("folio_ini", "folio_fin"):
        for raw in (folio_ini, folio_fin):
            n = _norm_folio(raw)
            if n:
                taken.add(n)
    for folio_ini, folio_fin in models.NotarizationReservation.objects.filter(
        idtipkar=idtipkar,
        status=models.NotarizationReservation.Status.PENDING,
    ).values_list("folio_ini", "folio_fin"):
        for raw in (folio_ini, folio_fin):
            n = _norm_folio(raw)
            if n:
                taken.add(n)
    return taken


def _last_folio_from_notarizations(*, year: int, idtipkar: int) -> str:
    """Folio anchor = folio_fin of the highest remaining num_escritura."""
    best_n = 0
    best_folio = ""
    for num_esc, folio_ini, folio_fin in models.Notarization.objects.filter(
        created_at__year=year,
        idtipkar=idtipkar,
    ).values_list("num_escritura", "folio_ini", "folio_fin"):
        n = _parse_positive_int(num_esc)
        if n < best_n:
            continue
        folio = (folio_fin or folio_ini or "").strip()
        if n > best_n or (n == best_n and folio):
            best_n = n
            best_folio = folio
    return best_folio


def _seed_defaults_from_history(*, year: int, idtipkar: int) -> dict:
    """Bootstrap counter from the highest committed escritura for year+tipo."""
    used = _notarization_nums(year=year, idtipkar=idtipkar)
    if not used:
        return {
            "next_num_escritura": 1,
            "next_num_minuta": 1,
            "last_folio": "",
            "freed_num_escrituras": [],
        }
    high = max(used)
    return {
        "next_num_escritura": high + 1,
        "next_num_minuta": 1,
        "last_folio": _last_folio_from_notarizations(year=year, idtipkar=idtipkar),
        "freed_num_escrituras": [],
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


def _next_fresh_folio(counter: models.CorrelativeCounter) -> str:
    if (counter.last_folio or "").strip():
        return correlatives.bump_folio_papel_string(counter.last_folio)
    return "1"


def allocate_correlatives(*, year: int, idtipkar: int) -> AllocatedCorrelatives:
    """
    Assign the next escritura/folio under a row lock and advance the escritura
    counter. Prefers the lowest freed hole (e.g. reversed 147 while 148/149
    remain), restoring that slot's original folio when still free.

    Does not allocate ``num_minuta`` — that field is clerk-entered only.
    """
    counter = get_locked_counter(year=year, idtipkar=idtipkar)
    taken = _notarization_nums(year=year, idtipkar=idtipkar) | _pending_reservation_nums(
        idtipkar=idtipkar
    )
    taken_folios = _taken_folios(year=year, idtipkar=idtipkar)

    slots = _normalize_freed_slots(counter.freed_num_escrituras)
    reusable = [
        s for s in slots
        if s["num_escritura"] not in taken
        and s["num_escritura"] < counter.next_num_escritura
    ]

    reused_folio = ""
    if reusable:
        slot = reusable[0]
        num_escritura_int = slot["num_escritura"]
        candidate_folio = (slot.get("folio") or "").strip()
        if candidate_folio and _norm_folio(candidate_folio) not in taken_folios:
            reused_folio = candidate_folio
        counter.freed_num_escrituras = [
            s for s in slots if s["num_escritura"] != num_escritura_int
        ]
        counter.save(update_fields=["freed_num_escrituras", "updated_at"])
    else:
        num_escritura_int = max(1, counter.next_num_escritura)
        while num_escritura_int in taken:
            num_escritura_int += 1
        counter.next_num_escritura = num_escritura_int + 1
        counter.freed_num_escrituras = [
            s
            for s in slots
            if s["num_escritura"] not in taken
            and s["num_escritura"] < counter.next_num_escritura
        ]
        counter.save(
            update_fields=["next_num_escritura", "freed_num_escrituras", "updated_at"]
        )

    folio = reused_folio or _next_fresh_folio(counter)

    return AllocatedCorrelatives(
        num_escritura=str(num_escritura_int),
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


def rebuild_counter_from_history(
    *,
    year: int,
    idtipkar: int,
    freed_num_escritura: str | int | None = None,
    freed_folio: str | None = None,
) -> models.CorrelativeCounter:
    """
    Reset next_escritura / last_folio from remaining committed notarizations.

    If ``freed_num_escritura`` is a hole below the new next (e.g. reverse 147
    while 148 and 149 remain), park it (with ``freed_folio``) so the next
    reserve reuses both.
    """
    counter = get_locked_counter(year=year, idtipkar=idtipkar)
    used = _notarization_nums(year=year, idtipkar=idtipkar)
    pending = _pending_reservation_nums(idtipkar=idtipkar)
    taken = used | pending

    high = max(taken) if taken else 0
    counter.next_num_escritura = high + 1 if high else 1
    counter.last_folio = _last_folio_from_notarizations(year=year, idtipkar=idtipkar)

    slots_by_num = {
        s["num_escritura"]: s.get("folio") or ""
        for s in _normalize_freed_slots(counter.freed_num_escrituras)
    }
    released = _parse_positive_int(
        str(freed_num_escritura) if freed_num_escritura is not None else ""
    )
    if released:
        folio = (freed_folio or "").strip()
        if released not in slots_by_num or (folio and not slots_by_num[released]):
            slots_by_num[released] = folio or slots_by_num.get(released, "")

    counter.freed_num_escrituras = [
        {"num_escritura": n, "folio": slots_by_num[n]}
        for n in sorted(slots_by_num)
        if n not in taken and n < counter.next_num_escritura
    ]
    counter.next_num_minuta = 1
    counter.save(
        update_fields=[
            "next_num_escritura",
            "next_num_minuta",
            "last_folio",
            "freed_num_escrituras",
            "updated_at",
        ]
    )
    return counter


def release_num_escritura(
    *,
    year: int,
    idtipkar: int,
    num_escritura: str | int | None,
    folio: str | None = None,
) -> models.CorrelativeCounter:
    """
    Return a number (and its folio) to the free pool
    (expired/cancelled pending reservation).
    """
    return rebuild_counter_from_history(
        year=year,
        idtipkar=idtipkar,
        freed_num_escritura=num_escritura,
        freed_folio=folio,
    )
