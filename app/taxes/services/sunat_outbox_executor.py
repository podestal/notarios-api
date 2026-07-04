"""
Execute one SUNAT outbox row (recibo or resumen).
"""

from __future__ import annotations

import logging

from django.db import transaction

from taxes.models import Recibos, Resumenes, SunatOutbox
from taxes.legacy_db import POSTGRES_DB
from taxes.services.sunat_errors import (
    is_transient_sunat_result,
    recibo_needs_sunat_retry,
    resumen_needs_sunat_retry,
    resumen_should_poll,
)
from taxes.services.sunat_outbox import (
    mark_outbox_completed,
    mark_outbox_failed,
    mark_outbox_processing,
    schedule_outbox_retry,
)
from taxes.services.xml.enviar import enviar_recibo_sunat
from taxes.services.xml.enviar_resumen import (
    consultar_ticket_resumen,
    procesar_resumen_sunat,
)

logger = logging.getLogger(__name__)


def _execute_recibo_outbox(outbox: SunatOutbox) -> SunatOutbox:
    recibo = Recibos.objects.using(POSTGRES_DB).filter(id_recibo=outbox.target_id).first()
    if not recibo:
        return mark_outbox_failed(outbox, error="Recibo no encontrado.")

    if recibo.aceptada_sunat:
        return mark_outbox_completed(outbox)

    sunat = enviar_recibo_sunat(recibo_id=outbox.target_id, raise_on_failure=False)
    if sunat.get("aceptada_sunat"):
        return mark_outbox_completed(outbox)

    if recibo_needs_sunat_retry(sunat):
        return schedule_outbox_retry(
            outbox,
            last_error=str(sunat.get("msj_sunat") or ""),
        )

    if is_transient_sunat_result(sunat):
        return schedule_outbox_retry(
            outbox,
            last_error=str(sunat.get("msj_sunat") or ""),
        )

    return mark_outbox_failed(
        outbox,
        error=str(sunat.get("msj_sunat") or "SUNAT rechazó el comprobante."),
    )


def _execute_resumen_poll(outbox: SunatOutbox) -> SunatOutbox:
    resumen = Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=outbox.target_id).first()
    if not resumen:
        return mark_outbox_failed(outbox, error="Resumen no encontrado.")

    if resumen.aceptada_sunat:
        return mark_outbox_completed(outbox)

    ticket = (outbox.metadata or {}).get("ticket") or resumen.ticket_sunat or ""
    consulta = consultar_ticket_resumen(
        resumen_id=outbox.target_id,
        ticket=ticket,
        raise_on_failure=False,
        max_polls=3,
        poll_interval_seconds=3.0,
    )
    if consulta.get("aceptada_sunat"):
        return mark_outbox_completed(outbox)

    if consulta.get("en_proceso") or is_transient_sunat_result(consulta):
        return schedule_outbox_retry(
            outbox,
            last_error=str(consulta.get("msj_sunat") or ""),
            phase=SunatOutbox.Phase.POLL,
            metadata={"ticket": ticket},
        )

    return mark_outbox_failed(
        outbox,
        error=str(consulta.get("msj_sunat") or "SUNAT rechazó el resumen."),
    )


def _execute_resumen_send(outbox: SunatOutbox) -> SunatOutbox:
    resumen = Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=outbox.target_id).first()
    if not resumen:
        return mark_outbox_failed(outbox, error="Resumen no encontrado.")

    if resumen.aceptada_sunat:
        return mark_outbox_completed(outbox)

    result = procesar_resumen_sunat(
        resumen_id=outbox.target_id,
        consultar_ticket=True,
        max_polls=5,
        poll_interval_seconds=3.0,
        raise_on_failure=False,
    )

    consulta = result.get("sunat_consulta") or {}
    envio = result.get("sunat_envio") or {}
    if consulta.get("aceptada_sunat") or envio.get("aceptada_sunat"):
        return mark_outbox_completed(outbox)

    ticket = (envio.get("ticket") or consulta.get("ticket") or "").strip()
    if resumen_should_poll(result):
        return schedule_outbox_retry(
            outbox,
            last_error=str(consulta.get("msj_sunat") or envio.get("msj_sunat") or ""),
            phase=SunatOutbox.Phase.POLL,
            metadata={"ticket": ticket},
        )

    if resumen_needs_sunat_retry(result):
        return schedule_outbox_retry(
            outbox,
            last_error=str(
                consulta.get("msj_sunat") or envio.get("msj_sunat") or ""
            ),
            phase=SunatOutbox.Phase.SEND,
        )

    return mark_outbox_failed(
        outbox,
        error=str(
            consulta.get("msj_sunat")
            or envio.get("msj_sunat")
            or "No se pudo enviar el resumen a SUNAT."
        ),
    )


@transaction.atomic
def execute_sunat_outbox(outbox_id: int, *, celery_task_id: str = "") -> SunatOutbox:
    outbox = SunatOutbox.objects.select_for_update().get(pk=outbox_id)

    if outbox.status == SunatOutbox.Status.COMPLETED:
        return outbox
    if outbox.status == SunatOutbox.Status.FAILED:
        return outbox

    mark_outbox_processing(outbox, celery_task_id=celery_task_id)

    try:
        if outbox.kind == SunatOutbox.Kind.RECIBO:
            return _execute_recibo_outbox(outbox)
        if outbox.phase == SunatOutbox.Phase.POLL:
            return _execute_resumen_poll(outbox)
        return _execute_resumen_send(outbox)
    except Exception as exc:
        logger.exception("SUNAT outbox %s failed: %s", outbox_id, exc)
        outbox.refresh_from_db()
        if outbox.status in (SunatOutbox.Status.COMPLETED, SunatOutbox.Status.FAILED):
            return outbox
        return schedule_outbox_retry(outbox, last_error=str(exc))
