"""
Canonical JSON shape for KardexComplianceCache.payload (version 1).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

PAYLOAD_VERSION = 1
SOURCE_UIF = "uif"
SOURCE_SISGEN = "sisgen"
SOURCE_PDT = "pdt"
SUPPORTED_SOURCES = frozenset({SOURCE_UIF, SOURCE_SISGEN})


def empty_pdt_block() -> Dict[str, Any]:
    return {
        "status": "pending",
        "has_errors": False,
        "error_count": 0,
        "errors": [],
        "note": "PDT collector not implemented yet",
    }


def build_uif_block(uif_result: Dict[str, Any]) -> Dict[str, Any]:
    errors = list(uif_result.get("uif_errors") or [])
    observations = list(uif_result.get("uif_observations") or [])
    error_count = len(errors)
    return {
        "has_errors": bool(uif_result.get("has_uif_errors")) or error_count > 0,
        "error_count": error_count,
        "observation_count": len(observations),
        "errors": errors,
        "observations": observations,
        "patrimonial_data": uif_result.get("patrimonial_data") or {},
    }


def build_sisgen_block(
    *,
    errores: List[str],
    observaciones: List[str],
    personas: List[str],
) -> Dict[str, Any]:
    errores = list(errores or [])
    personas = list(personas or [])
    observaciones = list(observaciones or [])
    error_count = len(errores) + len(personas)
    return {
        "has_errors": error_count > 0,
        "error_count": error_count,
        "observation_count": len(observaciones),
        "errores": errores,
        "observaciones": observaciones,
        "personas": personas,
    }


def build_payload(
    *,
    kardex: str,
    idkardex: str,
    idtipkar: Optional[int],
    kardex_meta: Dict[str, Any],
    uif_block: Dict[str, Any],
    sisgen_block: Dict[str, Any],
    validated_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    validated_at = validated_at or datetime.utcnow()
    by_source = {
        SOURCE_UIF: uif_block.get("error_count", 0),
        SOURCE_SISGEN: sisgen_block.get("error_count", 0),
        SOURCE_PDT: 0,
    }
    total_errors = by_source[SOURCE_UIF] + by_source[SOURCE_SISGEN]
    total_observations = (
        uif_block.get("observation_count", 0) + sisgen_block.get("observation_count", 0)
    )
    return {
        "version": PAYLOAD_VERSION,
        "validated_at": validated_at.isoformat() + "Z",
        "kardex_meta": kardex_meta,
        "sources": {
            SOURCE_UIF: uif_block,
            SOURCE_SISGEN: sisgen_block,
            SOURCE_PDT: empty_pdt_block(),
        },
        "summary": {
            "has_errors": total_errors > 0,
            "total_errors": total_errors,
            "total_observations": total_observations,
            "by_source": by_source,
        },
    }


def counts_from_payload(payload: Dict[str, Any]) -> Dict[str, int]:
    sources = payload.get("sources") or {}
    uif = sources.get(SOURCE_UIF) or {}
    sisgen = sources.get(SOURCE_SISGEN) or {}
    uif_count = int(uif.get("error_count") or 0)
    sisgen_count = int(sisgen.get("error_count") or 0)
    sisgen_obs = int(sisgen.get("observation_count") or 0)
    return {
        "uif_error_count": uif_count,
        "sisgen_error_count": sisgen_count,
        "sisgen_observation_count": sisgen_obs,
        "total_error_count": uif_count + sisgen_count,
        "has_errors": (uif_count + sisgen_count) > 0,
    }


def serialize_cache_row(
    row: "KardexComplianceCache",
    *,
    include_payload: bool = True,
    source_filter: Optional[str] = None,
) -> Dict[str, Any]:
    payload = row.payload or {}
    item = {
        "kardex": row.kardex,
        "idkardex": row.idkardex,
        "idtipkar": row.idtipkar,
        "fechaescritura": row.fechaescritura.isoformat() if row.fechaescritura else None,
        "validated_at": (payload.get("validated_at") or row.updated_at.isoformat()),
        "has_errors": row.has_errors,
        "counts": {
            "uif": row.uif_error_count,
            "sisgen": row.sisgen_error_count,
            "sisgen_observations": row.sisgen_observation_count,
            "total": row.total_error_count,
        },
        "summary": payload.get("summary") or {},
        "kardex_meta": (payload.get("kardex_meta") or {}),
    }
    if include_payload:
        item["payload"] = filter_payload_sources(payload, source_filter)
    return item


def filter_payload_sources(
    payload: Dict[str, Any], source_filter: Optional[str]
) -> Dict[str, Any]:
    if not source_filter or source_filter not in SUPPORTED_SOURCES:
        return payload
    sources = dict(payload.get("sources") or {})
    filtered = {key: sources.get(key) for key in sources if key == source_filter}
    filtered[SOURCE_PDT] = sources.get(SOURCE_PDT) or empty_pdt_block()
    out = dict(payload)
    out["sources"] = filtered
    summary = dict(out.get("summary") or {})
    by_source = dict(summary.get("by_source") or {})
    summary["by_source"] = {k: by_source.get(k, 0) for k in filtered if k != SOURCE_PDT}
    summary["total_errors"] = (filtered.get(SOURCE_UIF) or {}).get(
        "error_count", 0
    ) + (filtered.get(SOURCE_SISGEN) or {}).get("error_count", 0)
    summary["has_errors"] = summary["total_errors"] > 0
    out["summary"] = summary
    return out
