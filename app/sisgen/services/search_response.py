"""
Trim /sisgen/search/ payloads to fields consumed by the búsqueda SISGEN UI.
"""

from typing import Any, Dict


def slim_search_pagination(page_status: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "search_id": page_status.get("search_id"),
        "total_documents": page_status.get("total_documents"),
    }


def slim_sisgen_status(sync: Dict[str, Any]) -> Dict[str, Any]:
    sync = sync or {}
    return {
        "status_ui": sync.get("status_ui"),
        "needs_resubmit": sync.get("needs_resubmit"),
        "can_send": sync.get("can_send"),
        "estado_sisgen_label": sync.get("estado_sisgen_label"),
    }


def slim_sisgen_last_submission(last: Dict[str, Any]) -> Dict[str, Any]:
    last = last or {}
    if not last.get("exists"):
        return {"exists": False}
    out = {
        "exists": True,
        "status_ui": last.get("status_ui"),
        "errors": list(last.get("errors") or []),
    }
    if last.get("nota_contacto_it"):
        out["nota_contacto_it"] = last["nota_contacto_it"]
    return out


def count_sisgen_errors(row: Dict[str, Any]) -> int:
    """Pre-send SISGEN ``errores`` only (excludes observaciones, personas, UIF, PDT)."""
    return len(row.get("errores") or [])


def count_sisgen_observaciones(row: Dict[str, Any]) -> int:
    return len(row.get("observaciones") or [])


def count_sisgen_personas(row: Dict[str, Any]) -> int:
    return len(row.get("personas") or [])


def slim_search_document_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kardex": row.get("kardex"),
        "idkardex": row.get("idkardex"),
        "contrato": row.get("contrato"),
        "estado_sisgen": row.get("estado_sisgen"),
        "idtipkar": row.get("idtipkar"),
        "sisgen_error_count": count_sisgen_errors(row),
        "sisgen_observaciones_count": count_sisgen_observaciones(row),
        "sisgen_personas_count": count_sisgen_personas(row),
        "sisgen_status": slim_sisgen_status(row.get("sisgen_status") or {}),
        "sisgen_last_submission": slim_sisgen_last_submission(
            row.get("sisgen_last_submission") or {}
        ),
    }
