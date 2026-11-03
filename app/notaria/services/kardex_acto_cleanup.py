"""
Cascade delete for one act (idtipoacto) on a kardex.

Used when an act is removed from ``detalle_actos_kardex`` or ``kardex.codactos``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from notaria import models


def _normalize_condicion_entries(condicion_value) -> List[Tuple[str, str]]:
    if not condicion_value:
        return []

    normalized: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for raw in str(condicion_value).split("/"):
        raw = (raw or "").strip()
        if not raw or "." not in raw:
            continue
        idcondicion, item = raw.split(".", 1)
        idcondicion = idcondicion.strip()
        item = item.strip()
        if not idcondicion or not item:
            continue
        key = (idcondicion, item)
        if key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized


def _format_condicion_entries(pairs: Iterable[Tuple[str, str]]) -> str:
    return "".join(f"{idc}.{item}/" for idc, item in pairs)


def active_idtipoactos_for_kardex(kardex: str) -> Set[str]:
    if not kardex:
        return set()
    return {
        str(v).strip()
        for v in models.DetalleActosKardex.objects.filter(kardex=kardex).values_list(
            "idtipoacto", flat=True
        )
        if v is not None and str(v).strip()
    }


def idtipoactos_from_codactos(codactos: Optional[str]) -> Set[str]:
    raw = str(codactos or "").strip()
    if not raw:
        return set()
    return {raw[i : i + 3] for i in range(0, len(raw), 3) if raw[i : i + 3]}


def filter_participants_to_active_actos(
    participants: List[Dict[str, Any]],
    *,
    kardex: str,
    codactos: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Drop stale ``contratantesxacto`` rows whose ``idtipoacto`` is not on the kardex."""
    active = active_idtipoactos_for_kardex(kardex)
    if not active:
        active = idtipoactos_from_codactos(codactos)
    if not active:
        return participants

    filtered: List[Dict[str, Any]] = []
    for row in participants:
        idtipoacto = str(row.get("idtipoacto") or "").strip()
        if idtipoacto and idtipoacto in active:
            filtered.append(row)
    return filtered


def rebuild_contratantes_condicion_for_kardex(
    kardex: str,
    *,
    idcontratante: Optional[str] = None,
) -> int:
    """
    Rebuild ``contratantes.condicion`` from active ``contratantesxacto`` rows.

    Single source of truth after deletes — avoids stale ``043.xxx/`` leftovers.
    """
    kardex_key = str(kardex or "").strip()
    if not kardex_key:
        return 0

    active = active_idtipoactos_for_kardex(kardex_key)
    cxa_qs = models.Contratantesxacto.objects.filter(kardex=kardex_key)
    if idcontratante is not None:
        cxa_qs = cxa_qs.filter(idcontratante=idcontratante)

    pairs_by_contratante: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    seen: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    for row in cxa_qs:
        idtipoacto = str(row.idtipoacto or "").strip()
        if active and idtipoacto not in active:
            continue
        cid = str(row.idcontratante or "").strip()
        idcondicion = str(row.idcondicion or "").strip()
        item = str(row.item or "").strip()
        if not cid or not idcondicion or not item:
            continue
        key = (idcondicion, item)
        if key in seen[cid]:
            continue
        seen[cid].add(key)
        pairs_by_contratante[cid].append(key)

    contratantes_qs = models.Contratantes.objects.filter(kardex=kardex_key)
    if idcontratante is not None:
        contratantes_qs = contratantes_qs.filter(idcontratante=idcontratante)

    updated = 0
    for contratante in contratantes_qs:
        cid = str(contratante.idcontratante or "").strip()
        new_condicion = _format_condicion_entries(pairs_by_contratante.get(cid, []))
        if new_condicion != (contratante.condicion or ""):
            models.Contratantes.objects.filter(pk=contratante.pk).update(
                condicion=new_condicion
            )
            updated += 1
    return updated


def _sync_contratantes_condicion(
    *,
    kardex: str,
    removed_rows: List[models.Contratantesxacto],
) -> int:
    if not removed_rows:
        return 0

    pairs_by_contratante: Dict[str, Set[Tuple[str, str]]] = defaultdict(set)
    for row in removed_rows:
        idcontratante = str(row.idcontratante or "").strip()
        idcondicion = str(row.idcondicion or "").strip()
        item = str(row.item or "").strip()
        if not idcontratante or not idcondicion or not item:
            continue
        pairs_by_contratante[idcontratante].add((idcondicion, item))

    updated = 0
    for idcontratante, remove_pairs in pairs_by_contratante.items():
        contratante = (
            models.Contratantes.objects.filter(
                kardex=kardex, idcontratante=idcontratante
            ).first()
        )
        if not contratante:
            continue

        kept = [
            pair
            for pair in _normalize_condicion_entries(contratante.condicion)
            if pair not in remove_pairs
        ]
        new_condicion = _format_condicion_entries(kept)
        if new_condicion != (contratante.condicion or ""):
            models.Contratantes.objects.filter(pk=contratante.pk).update(
                condicion=new_condicion
            )
            updated += 1
    return updated


def delete_kardex_acto_related(*, kardex: str, idtipoacto: str) -> Dict[str, int]:
    """
    Remove all rows tied to ``(kardex, idtipoacto)`` and sync ``contratantes.condicion``.

    Returns per-table delete counts for logging/tests.
    """
    kardex_key = str(kardex or "").strip()
    acto_key = str(idtipoacto or "").strip()
    if not kardex_key or not acto_key:
        return {}

    counts: Dict[str, int] = defaultdict(int)

    cxa_qs = models.Contratantesxacto.objects.filter(
        kardex=kardex_key, idtipoacto=acto_key
    )
    removed_cxa = list(cxa_qs)
    counts["contratantes_condicion_updated"] = _sync_contratantes_condicion(
        kardex=kardex_key, removed_rows=removed_cxa
    )
    deleted_cxa, _ = cxa_qs.delete()
    counts["contratantesxacto"] = int(deleted_cxa)

    patrimonial_rows = list(
        models.Patrimonial.objects.filter(kardex=kardex_key, idtipoacto=acto_key)
    )
    itemmps = [str(p.itemmp).strip() for p in patrimonial_rows if p.itemmp]
    for itemmp in itemmps:
        deleted_mp, _ = models.Detallemediopago.objects.filter(itemmp=itemmp).delete()
        counts["detallemediopago"] += int(deleted_mp)
        deleted_bi, _ = models.Detallebienes.objects.filter(itemmp=itemmp).delete()
        counts["detallebienes"] += int(deleted_bi)

    deleted_pat, _ = models.Patrimonial.objects.filter(
        kardex=kardex_key, idtipoacto=acto_key
    ).delete()
    counts["patrimonial"] = int(deleted_pat)

    deleted_mp_orphan, _ = models.Detallemediopago.objects.filter(
        kardex=kardex_key, tipacto=acto_key
    ).delete()
    counts["detallemediopago"] += int(deleted_mp_orphan)

    deleted_bi_orphan, _ = models.Detallebienes.objects.filter(
        kardex=kardex_key, idtipacto=acto_key
    ).delete()
    counts["detallebienes"] += int(deleted_bi_orphan)

    deleted_veh, _ = models.Detallevehicular.objects.filter(
        kardex=kardex_key, idtipacto=acto_key
    ).delete()
    counts["detallevehicular"] = int(deleted_veh)

    deleted_rep, _ = models.Representantes.objects.filter(
        kardex=kardex_key, idtipoacto=acto_key
    ).delete()
    counts["representantes"] = int(deleted_rep)

    deleted_detalle, _ = models.DetalleActosKardex.objects.filter(
        kardex=kardex_key, idtipoacto=acto_key
    ).delete()
    counts["detalle_actos_kardex"] = int(deleted_detalle)

    counts["contratantes_condicion_rebuilt"] = rebuild_contratantes_condicion_for_kardex(
        kardex_key
    )

    return dict(counts)


def active_detalle_item_by_acto(kardex: str) -> Dict[str, str]:
    """Map ``idtipoacto -> detalle_actos_kardex.item`` for the kardex."""
    kardex_key = str(kardex or "").strip()
    if not kardex_key:
        return {}
    return {
        str(row.idtipoacto).strip(): str(row.item)
        for row in models.DetalleActosKardex.objects.filter(kardex=kardex_key)
        if row.idtipoacto is not None and str(row.idtipoacto).strip()
    }


def resolve_condition_pairs_for_kardex(
    kardex: str,
    pairs: Iterable[Tuple[str, str]],
) -> List[Tuple[str, str]]:
    """
    Keep only conditions whose acto is still on the kardex.

    Remaps ``item`` to the current ``detalle_actos_kardex.item`` for that acto so a
    stale ``049.6027/`` after an acto recreate becomes ``049.6028/`` instead of
    creating an orphan ``contratantesxacto`` row.
    """
    detalle_by_acto = active_detalle_item_by_acto(kardex)
    if not detalle_by_acto:
        return []

    resolved: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for idcondicion, _item in pairs:
        idc = str(idcondicion or "").strip()
        if not idc:
            continue
        acto_condicion = (
            models.Actocondicion.objects.filter(idcondicion=idc).first()
        )
        if not acto_condicion:
            continue
        acto = str(acto_condicion.idtipoacto or "").strip()
        current_item = detalle_by_acto.get(acto)
        if current_item is None:
            continue
        key = (idc, current_item)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(key)
    return resolved


def purge_orphan_contratantesxacto_for_kardex(kardex: str) -> Dict[str, int]:
    """
    Delete leftover ``contratantesxacto`` (and related acto data) that no longer
    match ``detalle_actos_kardex`` for this kardex.

    Covers:
    - acto removed / changed (e.g. 030 → 028) without a full cascade
    - stale ``item`` after detalle was recreated for the same acto
    """
    kardex_key = str(kardex or "").strip()
    if not kardex_key:
        return {}

    counts: Dict[str, int] = defaultdict(int)
    active_actos = active_idtipoactos_for_kardex(kardex_key)
    active_items = {
        row.item
        for row in models.DetalleActosKardex.objects.filter(kardex=kardex_key)
    }

    orphan_actos = {
        str(v).strip()
        for v in models.Contratantesxacto.objects.filter(kardex=kardex_key)
        .values_list("idtipoacto", flat=True)
        .distinct()
        if v is not None and str(v).strip() and str(v).strip() not in active_actos
    }
    for orphan_acto in orphan_actos:
        sub = delete_kardex_acto_related(kardex=kardex_key, idtipoacto=orphan_acto)
        for key, value in sub.items():
            counts[key] += int(value or 0)

    stale_item_qs = models.Contratantesxacto.objects.filter(kardex=kardex_key)
    if active_items:
        stale_item_qs = stale_item_qs.exclude(item__in=active_items)
    removed_stale = list(stale_item_qs)
    if removed_stale:
        counts["contratantes_condicion_updated"] += _sync_contratantes_condicion(
            kardex=kardex_key, removed_rows=removed_stale
        )
        deleted_stale, _ = stale_item_qs.delete()
        counts["contratantesxacto_stale_item"] = int(deleted_stale)
        counts["contratantes_condicion_rebuilt"] += (
            rebuild_contratantes_condicion_for_kardex(kardex_key)
        )

    return dict(counts)
