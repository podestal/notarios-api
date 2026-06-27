"""Exclude kardex already accepted by SISGEN from compliance error reporting."""

from __future__ import annotations

from typing import List, Tuple

from notaria import models
from sisgen.services.sync_status import estado_label, normalize_estado_sisgen_code

# 1 = Enviado (GUARDADO), 2 = Enviado (Observado) — SISGEN already accepted the expediente.
SISGEN_SENT_ESTADO_CODES = frozenset({1, 2})


def sisgen_estado_code(estado_sisgen) -> int:
    code = normalize_estado_sisgen_code(estado_sisgen)
    return 0 if code is None else code


def is_kardex_sent_to_sisgen(estado_sisgen) -> bool:
    return sisgen_estado_code(estado_sisgen) in SISGEN_SENT_ESTADO_CODES


def partition_kardex_by_sisgen_sent(
    kardex_models: List[models.Kardex],
) -> Tuple[List[models.Kardex], List[models.Kardex]]:
    eligible: List[models.Kardex] = []
    sent: List[models.Kardex] = []
    for row in kardex_models:
        if is_kardex_sent_to_sisgen(row.estado_sisgen):
            sent.append(row)
        else:
            eligible.append(row)
    return eligible, sent


def sisgen_sent_meta(kardex_row: models.Kardex) -> dict:
    code = sisgen_estado_code(kardex_row.estado_sisgen)
    return {
        "sisgen_sent": True,
        "estado_sisgen_code": code,
        "estado_sisgen_label": estado_label(code),
        "note": "Kardex ya enviado a SISGEN; no se reportan errores de cumplimiento.",
    }
