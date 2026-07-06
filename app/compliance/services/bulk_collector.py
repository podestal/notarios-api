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
from compliance.services.sisgen_collector import bulk_collect_sisgen_issue_counts
from uif.services.kardex_snapshot import bulk_count_uif_errors
from uif.services.load_data import _parse_act_codes

logger = logging.getLogger(__name__)


def _count_sisgen_errores(keys: List[str]) -> Dict[str, int]:
    bulk = bulk_collect_sisgen_issue_counts(keys)
    return {k: int(bulk.get(k, {}).get("error_count") or 0) for k in keys}


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
        for t in models.Tiposdeacto.objects.filter(idtipoacto__in=all_act_codes).only(
            "idtipoacto", "actouif", "desacto"
        ):
            tipo_by_act[str(t.idtipoacto)] = t

    kardex_by_key = {str(k.kardex).strip(): k for k in kardex_rows if k.kardex}

    with ThreadPoolExecutor(max_workers=2) as pool:
        sisgen_future = pool.submit(_count_sisgen_errores, keys)
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
