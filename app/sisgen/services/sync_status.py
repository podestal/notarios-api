"""
SISGEN sync state: kardex.estado_sisgen (workflow) vs last SOAP response (audit).

The UI must not treat last SisgenSoapResponse alone as «current» status after edits:
_reset_sisgen_for_kardex sets estado_sisgen=0 while the response row still says GUARDADO.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from sisgen.utils.constants import ESTADO_SISGEN_MAPPING


def normalize_estado_sisgen_code(estado: Any) -> Optional[int]:
    """Same rules as DocumentSearchService._normalize_estado_sisgen_code."""
    if estado is None:
        return None
    if isinstance(estado, bytes):
        estado = estado.decode("utf-8", errors="ignore").strip()
    if isinstance(estado, Decimal):
        try:
            return int(estado)
        except (ValueError, OverflowError, ArithmeticError):
            return None
    if isinstance(estado, float):
        if estado != estado:
            return None
        try:
            return int(estado)
        except ValueError:
            return None
    if isinstance(estado, str):
        s = estado.strip()
        if s == "":
            return 0
        if s.upper() in {"NULL", "NONE", "-"}:
            return None
        try:
            return int(float(s)) if "." in s else int(s)
        except ValueError:
            return None
    try:
        return int(estado)
    except (TypeError, ValueError):
        return None


def status_ui_from_document_status(status_text: str) -> str:
    s = (status_text or "").strip().upper()
    if s == "GUARDADO":
        return "guardado"
    if s == "CON OBSERVACIONES":
        return "observado"
    if s == "FALLIDO":
        return "fallido"
    return "pendiente"


def status_ui_from_estado_code(estado_code: Optional[int]) -> str:
    if estado_code in (None, 0):
        return "pendiente"
    if estado_code == 1:
        return "guardado"
    if estado_code == 2:
        return "observado"
    if estado_code == 3:
        return "fallido"
    if estado_code == 4:
        return "sin_codigo_ancert"
    return "pendiente"


def estado_label(estado_code: Optional[int]) -> str:
    key = 0 if estado_code is None else estado_code
    label = ESTADO_SISGEN_MAPPING.get(key)
    if label is not None:
        return label
    if estado_code is None:
        return "Sin estado SISGEN"
    return f"Código {estado_code} (sin etiqueta)"


def build_sisgen_sync_status(
    estado_code: Optional[int],
    last_submission: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Effective status for UI and send workflow.

    ``status_ui`` is what the grid should show. When the expediente was edited after
    a successful send, ``needs_resubmit`` is True and ``status_ui`` is
    ``pendiente_reenvio`` even if ``last_submission.document_status`` is GUARDADO.
    """
    last = dict(last_submission or {"exists": False})
    if last.get("exists"):
        doc_st = (last.get("document_status") or "").strip().upper()
        last.setdefault(
            "remote_status_ui",
            status_ui_from_document_status(last.get("document_status") or ""),
        )
        last["remote_document_status"] = doc_st or last.get("document_status")

    code = normalize_estado_sisgen_code(estado_code)
    if code is None:
        code = 0

    had_remote = bool(last.get("exists"))
    remote_was_sent = had_remote and (last.get("remote_document_status") or "") in (
        "GUARDADO",
        "CON OBSERVACIONES",
        "FALLIDO",
        "OK_ACK",
    )

    needs_resubmit = code == 0 and remote_was_sent
    submission_stale = needs_resubmit

    if needs_resubmit:
        effective_ui = "pendiente_reenvio"
        effective_label = "Pendiente reenvío (datos modificados)"
    else:
        effective_ui = status_ui_from_estado_code(code)
        effective_label = estado_label(code)

    can_send = code in (0, 3) or needs_resubmit

    return {
        "estado_sisgen_code": code,
        "estado_sisgen_label": effective_label,
        "status_ui": effective_ui,
        "needs_resubmit": needs_resubmit,
        "submission_stale": submission_stale,
        "can_send": can_send,
        "last_submission": last,
    }


def merge_last_submission_for_row(
    last_submission: Dict[str, Any],
    sync: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Enrich sisgen_last_submission for clients that only read that object.

    ``status_ui`` is overridden to the effective value; remote SOAP status is preserved.
    """
    out = dict(last_submission)
    out["status_ui"] = sync["status_ui"]
    out["needs_resubmit"] = sync["needs_resubmit"]
    out["submission_stale"] = sync["submission_stale"]
    out["estado_sisgen_code"] = sync["estado_sisgen_code"]
    out["estado_sisgen_label"] = sync["estado_sisgen_label"]
    out["can_send"] = sync["can_send"]
    if out.get("exists"):
        out.setdefault(
            "remote_status_ui",
            status_ui_from_document_status(out.get("document_status") or ""),
        )
    return out
