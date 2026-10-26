import logging
import os
import re
from typing import Any, Optional

from ducumentation.storage import sanitize_uploaded_docx_filename

logger = logging.getLogger(__name__)

TABLE_DOCUMENTO = "documento"

_KARDEX_AUDIT_ACTIONS = {
    "G": "create",
    "U": "update",
    "S": "update",
}

_ACTION_LABELS = {
    "G": "Generó el documento",
    "U": "Actualizó el documento",
    "S": "Guardó el documento",
    "O": "Abrió el documento",
}


def kardex_from_proyecto_filename(filename: str) -> str:
    raw = os.path.basename(str(filename or "").strip())
    try:
        raw = sanitize_uploaded_docx_filename(raw)
    except Exception:
        pass
    match = re.search(r"__PROY__(.+?)\.docx$", raw, flags=re.IGNORECASE)
    return (match.group(1) if match else "").strip()


def resolve_digitacion_user(kardex: str):
    if not kardex:
        return None
    try:
        from ducumentation.models import Documentogenerados, DocumentosLogs
        from django.contrib.auth import get_user_model

        log = (
            DocumentosLogs.objects.filter(kardex=kardex)
            .select_related("user")
            .order_by("-created_at", "-id")
            .first()
        )
        if log and getattr(log, "user", None):
            return log.user
        doc = Documentogenerados.objects.filter(kardex=kardex).first()
        user_id = getattr(doc, "usuario", None) if doc else None
        if user_id:
            return get_user_model().objects.filter(idusuario=user_id).first()
    except Exception:
        logger.exception("Could not resolve digitacion user for %s", kardex)
    return None


def log_digitacion_document(
    *,
    kardex: str,
    user: Any = None,
    action: str,
    source: str = "",
    filename: str = "",
) -> None:
    """Write digitacion DocumentosLogs and a kardex historial row. Never raises."""
    kardex = (kardex or "").strip()
    action = (action or "").strip().upper()[:1]
    if not kardex or action not in _ACTION_LABELS:
        return
    filename = filename or f"__PROY__{kardex}.docx"
    actor = user or resolve_digitacion_user(kardex)

    try:
        from ducumentation.models import DocumentosLogs

        if actor is not None and getattr(actor, "is_authenticated", True):
            DocumentosLogs.objects.create(kardex=kardex, user=actor, action=action)
    except Exception:
        logger.exception("Failed to write DocumentosLogs for %s %s", kardex, action)

    audit_action = _KARDEX_AUDIT_ACTIONS.get(action)
    if not audit_action:
        return
    try:
        from audit.services import enqueue_manual_event

        enqueue_manual_event(
            kardex=kardex,
            table_name=TABLE_DOCUMENTO,
            action=audit_action,
            record_pk=filename,
            changes={
                "Acción": {"old": None, "new": _ACTION_LABELS[action]},
                "Archivo": {"old": None, "new": filename},
            },
            source=source,
            user=actor,
        )
    except Exception:
        logger.exception("Failed to enqueue digitacion kardex log for %s %s", kardex, action)
