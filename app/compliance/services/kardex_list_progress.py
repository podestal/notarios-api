"""
One progress tone per kardex for the list.

Uses the same stage services as the open rail (no parallel local rules).
Collectors are memoized for the request and tones are built in parallel so a
page does not re-run SISGEN/UIF/PDT three times per row.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Tuple

from django.db import connection

from notaria import models

from compliance.services.collector_cache import CollectorCache, collector_cache_scope
from compliance.services.contratantes_progress import ContratantesProgressService
from compliance.services.instrumento_progress import InstrumentoProgressService
from compliance.services.participa_progress import (
    WITHOUT_PARTICIPA,
    ParticipaProgressService,
    _clean,
)
from compliance.services.patrimonial_progress import (
    WITHOUT_PATRIMONIAL,
    PatrimonialProgressService,
)

STAGE_POINTS = 4
ERROR_POINTS = 1
MAX_KEYS = 40
MAX_WORKERS = 8

TONE_INCOMPLETE = "incomplete"
TONE_WARNING = "warning"
TONE_COMPLETE = "complete"


def list_tone(leaves: Iterable[str], error_count: int, warning_count: int) -> str:
    """Match the rail: 100% needs every leaf finished and zero errors."""
    leaf_list = list(leaves)
    done = sum(1 for status in leaf_list if status in ("done", "warning"))
    maximum = len(leaf_list) * STAGE_POINTS + error_count * ERROR_POINTS
    earned = done * STAGE_POINTS
    raw = 0 if maximum == 0 else int((earned / maximum) * 100 + 0.5)
    percent = min(raw, 99) if error_count else raw
    if error_count or percent < 100:
        return TONE_INCOMPLETE
    if warning_count:
        return TONE_WARNING
    return TONE_COMPLETE


def score_stages(
    *,
    tipkar: int,
    contratantes: Dict[str, Any],
    patrimonial: Dict[str, Any] | None,
    participa: Dict[str, Any] | None,
    instrumento: Dict[str, Any],
) -> str:
    """Same leaf / warning / error weights as the open rail completion score."""
    leaves: List[str] = []
    errors = 0
    warnings = 0

    leaves.append(_status(contratantes))
    e, w = _issue_counts(contratantes.get("issues") or [])
    errors += e
    warnings += w

    if tipkar not in WITHOUT_PATRIMONIAL and patrimonial is not None:
        by_id = {step["id"]: step for step in patrimonial.get("steps") or []}
        for step_id in ("patrimonial", "medio-pago", "detalle-bien"):
            step = by_id.get(step_id) or {}
            e, w = _issue_counts(step.get("issues") or [])
            errors += e
            warnings += w
        leaves.append(_status(by_id.get("medio-pago") or {}))
        leaves.append(_status(by_id.get("detalle-bien") or {}))

    if tipkar not in WITHOUT_PARTICIPA and participa is not None:
        by_id = {step["id"]: step for step in participa.get("steps") or []}
        for step_id in ("participa", "preguntas-uif"):
            step = by_id.get(step_id) or {}
            e, w = _issue_counts(step.get("issues") or [])
            errors += e
            warnings += w
        leaves.append(_status(by_id.get("preguntas-uif") or {}))

    by_id = {step["id"]: step for step in instrumento.get("steps") or []}
    for step_id in ("digitacion", "escrituracion"):
        step = by_id.get(step_id) or {}
        e, w = _issue_counts(step.get("issues") or [])
        errors += e
        warnings += w
        leaves.append(_status(step))

    return list_tone(leaves, errors, warnings)


class KardexListProgressService:
    def summarize(self, keys: Iterable[str]) -> Dict[str, str]:
        ordered = _keys(keys)
        if not ordered:
            return {}

        rows = {
            _clean(row.kardex): row
            for row in models.Kardex.objects.filter(kardex__in=ordered).only(
                "kardex",
                "idtipkar",
                "estado_sisgen",
                "numescritura",
            )
        }
        jobs = []
        for key in ordered:
            row = rows.get(key)
            if row is None:
                continue
            try:
                tipkar = int(row.idtipkar or 0)
            except (TypeError, ValueError):
                tipkar = 0
            jobs.append((key, tipkar))

        out: Dict[str, str] = {key: TONE_INCOMPLETE for key in ordered if key not in rows}
        if not jobs:
            return {key: TONE_INCOMPLETE for key in ordered}

        cache = CollectorCache()
        workers = min(MAX_WORKERS, len(jobs))
        with collector_cache_scope(cache):
            if workers == 1:
                for key, tipkar in jobs:
                    out[key] = _tone_for_kardex(key, tipkar, cache)
            else:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {
                        pool.submit(_tone_for_kardex, key, tipkar, cache): key
                        for key, tipkar in jobs
                    }
                    for future in as_completed(futures):
                        key = futures[future]
                        try:
                            out[key] = future.result()
                        except Exception:
                            out[key] = TONE_INCOMPLETE
        return out


def _tone_for_kardex(key: str, tipkar: int, cache: CollectorCache) -> str:
    with collector_cache_scope(cache):
        try:
            return _score_kardex(key, tipkar)
        finally:
            connection.close()


def _score_kardex(key: str, tipkar: int) -> str:
    try:
        contratantes = ContratantesProgressService().build(key)
    except LookupError:
        return TONE_INCOMPLETE

    patrimonial = None
    if tipkar not in WITHOUT_PATRIMONIAL:
        try:
            patrimonial = PatrimonialProgressService().build(key)
        except LookupError:
            patrimonial = {"status": "idle", "steps": []}

    participa = None
    if tipkar not in WITHOUT_PARTICIPA:
        try:
            participa = ParticipaProgressService().build(key)
        except LookupError:
            participa = {"status": "idle", "steps": []}

    try:
        instrumento = InstrumentoProgressService().build(key)
    except LookupError:
        instrumento = {
            "status": "idle",
            "steps": [
                {"id": "digitacion", "status": "idle", "issues": []},
                {"id": "escrituracion", "status": "idle", "issues": []},
            ],
        }

    return score_stages(
        tipkar=tipkar,
        contratantes=contratantes,
        patrimonial=patrimonial,
        participa=participa,
        instrumento=instrumento,
    )


def _keys(keys: Iterable[str]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for raw in keys:
        key = _clean(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
        if len(ordered) >= MAX_KEYS:
            break
    return ordered


def _status(payload: Dict[str, Any]) -> str:
    status = _clean(payload.get("status"))
    return status if status in {"done", "warning", "error", "idle"} else "idle"


def _issue_counts(issues: List[Dict[str, str]]) -> Tuple[int, int]:
    errors = sum(1 for item in issues if item.get("level") == "error")
    warnings = sum(1 for item in issues if item.get("level") == "warning")
    return errors, warnings
