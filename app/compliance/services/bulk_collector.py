"""
Single-pass live compliance counts (SISGEN errores + UIF errors).

Loads each kardex once, batch-prefetches related rows, then validates in memory.
No KardexComplianceCache required.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from notaria import models
from sisgen.services.document_search_service import DocumentSearchService
from uif.services.kardex_snapshot import bulk_count_uif_errors
from uif.services.load_data import _parse_act_codes

logger = logging.getLogger(__name__)


def _sisgen_docs_from_kardex_rows(
    kardex_rows: List[models.Kardex],
    tipo_by_act: Dict[str, models.Tiposdeacto],
) -> List[dict]:
    docs: List[dict] = []
    for row in kardex_rows:
        key = str(row.kardex or "").strip()
        if not key:
            continue
        act_codes = _parse_act_codes(row.codactos or "")
        first_act = act_codes[0] if act_codes else None
        tipo = tipo_by_act.get(str(first_act)) if first_act else None
        cod_ancert = ""
        if tipo and tipo.cod_ancert:
            cod_ancert = str(tipo.cod_ancert)
        docs.append(
            {
                "idkardex": row.idkardex,
                "kardex": key,
                "numescritura": row.numescritura,
                "fechaescritura": row.fechaescritura,
                "cod_ancert": cod_ancert,
                "idtipkar": row.idtipkar,
                "codactos": row.codactos,
            }
        )
    return docs


def _count_sisgen_errores(docs: List[dict], keys: List[str]) -> Dict[str, int]:
    service = DocumentSearchService()
    service.kardex_errors = {}
    service.kardex_observations = {}
    service.person_errors = {}
    service.pdt_errors = {}

    try:
        prefetch = service._prefetch_document_validation_data(keys)
        service._validate_document_data(docs, validation_prefetch=prefetch)
    except Exception as exc:
        logger.warning("SISGEN batch validation warning: %s", exc)

    return {k: len(service.kardex_errors.get(k, [])) for k in keys}


def bulk_collect_compliance_error_counts(
    kardex_rows: List[models.Kardex],
) -> Dict[str, Dict[str, int]]:
    """
    Live validation counts for many kardex in one pass.

    Returns ``{kardex: {"sisgen": n, "uif": n}}``.
    """
    keys = [str(k.kardex).strip() for k in kardex_rows if k.kardex and str(k.kardex).strip()]
    if not keys:
        return {}

    all_act_codes: set = set()
    for row in kardex_rows:
        all_act_codes.update(_parse_act_codes(row.codactos or ""))

    tipo_by_act: Dict[str, models.Tiposdeacto] = {}
    if all_act_codes:
        for t in models.Tiposdeacto.objects.filter(idtipoacto__in=all_act_codes):
            tipo_by_act[str(t.idtipoacto)] = t

    docs = _sisgen_docs_from_kardex_rows(kardex_rows, tipo_by_act)
    kardex_by_key = {str(k.kardex).strip(): k for k in kardex_rows if k.kardex}

    with ThreadPoolExecutor(max_workers=2) as pool:
        sisgen_future = pool.submit(_count_sisgen_errores, docs, keys)
        uif_future = pool.submit(
            bulk_count_uif_errors,
            keys,
            kardex_by_key=kardex_by_key,
            tipo_by_act=tipo_by_act,
        )
        sisgen_counts = sisgen_future.result()
        uif_counts = uif_future.result()

    return {
        k: {
            "sisgen": int(sisgen_counts.get(k) or 0),
            "uif": int(uif_counts.get(k) or 0),
        }
        for k in keys
    }
