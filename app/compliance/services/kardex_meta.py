"""Kardex metadata attached to compliance payloads."""

from datetime import date, datetime
from typing import Any, Dict, Optional

from notaria import models


def parse_kardex_date(value) -> Optional[date]:
    if not value:
        return None
    if hasattr(value, "year"):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def kardex_meta_from_model(kardex: models.Kardex) -> Dict[str, Any]:
    return {
        "kardex": kardex.kardex or "",
        "idkardex": str(kardex.idkardex or ""),
        "idtipkar": kardex.idtipkar,
        "numescritura": kardex.numescritura or "",
        "codactos": kardex.codactos or "",
        "contrato": (kardex.contrato or "")[:200],
        "fechaescritura": str(kardex.fechaescritura or ""),
        "fechaconclusion": kardex.fechaconclusion or "",
    }
