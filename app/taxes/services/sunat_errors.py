"""
Classify SUNAT send outcomes for retry vs permanent failure.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

TRANSIENT_MARKERS = (
    "error de conexión con sunat",
    "error de conexion con sunat",
    "connection",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "service unavailable",
    "servicio no disponible",
    "no disponible",
    "502",
    "503",
    "504",
    "connection reset",
    "connection refused",
    "failed to establish",
    "name or service not known",
)


def is_transient_sunat_message(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return True
    return any(marker in text for marker in TRANSIENT_MARKERS)


def is_transient_sunat_result(result: Optional[Dict[str, Any]]) -> bool:
    if not result:
        return True

    if result.get("aceptada_sunat"):
        return False

    cod = str(result.get("cod_sunat") or "").strip()
    if cod and cod not in {"98", "0098"}:
        return False

    if result.get("enviada_sunat") and cod and cod not in {"98", "0098"}:
        return False

    if result.get("en_proceso"):
        return True

    message = str(result.get("msj_sunat") or result.get("message") or "")
    return is_transient_sunat_message(message)


def recibo_needs_sunat_retry(sunat: Optional[Dict[str, Any]]) -> bool:
    if not sunat:
        return False
    if sunat.get("aceptada_sunat"):
        return False
    if sunat.get("enviada_sunat") and not is_transient_sunat_result(sunat):
        return False
    return is_transient_sunat_result(sunat)


def resumen_needs_sunat_retry(result: Optional[Dict[str, Any]]) -> bool:
    if not result:
        return False

    consulta = result.get("sunat_consulta") or {}
    envio = result.get("sunat_envio") or {}

    if consulta.get("aceptada_sunat") or envio.get("aceptada_sunat"):
        return False

    if consulta.get("en_proceso"):
        return True

    if is_transient_sunat_result(consulta):
        return True
    return is_transient_sunat_result(envio)


def resumen_should_poll(result: Optional[Dict[str, Any]]) -> bool:
    if not result:
        return False
    consulta = result.get("sunat_consulta") or {}
    envio = result.get("sunat_envio") or {}
    if consulta.get("aceptada_sunat"):
        return False
    ticket = (envio.get("ticket") or consulta.get("ticket") or "").strip()
    if not ticket:
        return False
    return bool(consulta.get("en_proceso")) or is_transient_sunat_result(consulta)


def build_sunat_user_payload(
    *,
    sunat: Optional[Dict[str, Any]],
    outbox=None,
) -> Dict[str, Any]:
    sunat = dict(sunat or {})
    if sunat.get("aceptada_sunat"):
        return {
            **sunat,
            "status": "accepted",
            "recoverable": False,
            "message": sunat.get("msj_sunat") or "Comprobante aceptado por SUNAT.",
        }

    if outbox and outbox.status in (
        outbox.Status.PENDING,
        outbox.Status.PROCESSING,
    ):
        # Ticket already issued — waiting for CDR is normal for resumen/baja.
        if getattr(outbox, "phase", None) == outbox.Phase.POLL:
            return {
                **sunat,
                "status": "pending_ticket",
                "recoverable": True,
                "message": (
                    "SUNAT recibió el resumen (ticket emitido). "
                    "El CDR aún está en proceso; el sistema consultará el ticket automáticamente."
                ),
                "next_retry_at": outbox.next_retry_at.isoformat(),
                "retry_count": outbox.attempt_count,
                "last_error": outbox.last_error,
                "ticket": (outbox.metadata or {}).get("ticket")
                or sunat.get("ticket")
                or "",
            }
        return {
            **sunat,
            "status": "sunat_down",
            "recoverable": True,
            "message": (
                "SUNAT no está disponible en este momento. "
                "El comprobante fue generado y firmado; "
                "el sistema reintentará el envío automáticamente."
            ),
            "next_retry_at": outbox.next_retry_at.isoformat(),
            "retry_count": outbox.attempt_count,
            "last_error": outbox.last_error,
        }

    if sunat.get("en_proceso") and sunat.get("ticket"):
        return {
            **sunat,
            "status": "pending_ticket",
            "recoverable": True,
            "message": (
                sunat.get("msj_sunat")
                or "SUNAT recibió el resumen; el CDR está en proceso."
            ),
        }

    if sunat.get("enviada_sunat") and not sunat.get("aceptada_sunat"):
        return {
            **sunat,
            "status": "rejected",
            "recoverable": False,
            "message": sunat.get("msj_sunat") or "SUNAT rechazó el comprobante.",
        }

    if is_transient_sunat_result(sunat):
        return {
            **sunat,
            "status": "sunat_down",
            "recoverable": True,
            "message": (
                sunat.get("msj_sunat")
                or "SUNAT no está disponible; se reintentará automáticamente."
            ),
        }

    return {
        **sunat,
        "status": "rejected",
        "recoverable": False,
        "message": sunat.get("msj_sunat") or "No se pudo enviar a SUNAT.",
    }
