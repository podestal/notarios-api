"""Exclude kardex without escrituración (número de instrumento) from compliance errors."""

from __future__ import annotations

from typing import List, Tuple

from notaria import models


def normalized_numescritura(value) -> str:
    return str(value or "").strip()


def has_escrituracion_info(kardex_row: models.Kardex) -> bool:
    """Kardex is done for compliance when the notary recorded número de instrumento."""
    return bool(normalized_numescritura(kardex_row.numescritura))


def partition_kardex_by_escrituracion(
    kardex_models: List[models.Kardex],
) -> Tuple[List[models.Kardex], List[models.Kardex]]:
    ready: List[models.Kardex] = []
    pending: List[models.Kardex] = []
    for row in kardex_models:
        if has_escrituracion_info(row):
            ready.append(row)
        else:
            pending.append(row)
    return ready, pending


def escrituracion_pending_meta(kardex_row: models.Kardex) -> dict:
    return {
        "escrituracion_pending": True,
        "numescritura": normalized_numescritura(kardex_row.numescritura),
        "note": (
            "Kardex sin número de instrumento (escrituración); "
            "no se reportan errores de cumplimiento hasta que esté concluido."
        ),
    }
