"""
Trim /sisgen/search/ payloads to fields consumed by the búsqueda SISGEN UI.
"""

from typing import Any, Dict, List


def slim_search_pagination(page_status: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "search_id": page_status.get("search_id"),
        "total_documents": page_status.get("total_documents"),
    }


def slim_uif_validation(block: Dict[str, Any]) -> Dict[str, Any]:
    block = block or {}
    slim_errors: List[Dict[str, str]] = []
    for item in block.get("errors") or []:
        if isinstance(item, dict):
            desc = item.get("error_description")
            if desc:
                slim_errors.append({"error_description": str(desc)})
        elif item:
            slim_errors.append({"error_description": str(item)})
    return {
        "has_errors": bool(block.get("has_errors")),
        "errors": slim_errors,
        "observations": list(block.get("observations") or []),
    }


def slim_pdt_validation(block: Dict[str, Any]) -> Dict[str, Any]:
    block = block or {}
    return {
        "has_errors": bool(block.get("has_errors")),
        "errors": list(block.get("errors") or []),
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
    return {
        "exists": True,
        "status_ui": last.get("status_ui"),
        "errors": list(last.get("errors") or []),
    }


def slim_search_document_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kardex": row.get("kardex"),
        "idkardex": row.get("idkardex"),
        "contrato": row.get("contrato"),
        "estado_sisgen": row.get("estado_sisgen"),
        "idtipkar": row.get("idtipkar"),
        "errores": list(row.get("errores") or []),
        "observaciones": list(row.get("observaciones") or []),
        "personas": list(row.get("personas") or []),
        "sisgen_status": slim_sisgen_status(row.get("sisgen_status") or {}),
        "sisgen_last_submission": slim_sisgen_last_submission(
            row.get("sisgen_last_submission") or {}
        ),
        "uif_validation": slim_uif_validation(row.get("uif_validation") or {}),
        "pdt_validation": slim_pdt_validation(row.get("pdt_validation") or {}),
    }
