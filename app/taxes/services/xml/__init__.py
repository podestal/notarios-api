from .firmar import firmar_recibo_xml
from .generar import generar_recibo_xml
from .enviar import can_enviar_recibo_sunat, enviar_recibo_sunat, should_auto_enviar_sunat
from .enviar_baja import (
    consultar_ticket_baja,
    enviar_baja_sunat,
    procesar_baja_sunat,
)
from .enviar_resumen import (
    consultar_ticket_resumen,
    enviar_resumen_sunat,
    procesar_resumen_sunat,
)
from .context import fetch_recibo_xml_context
from .paths import firmar_dir, generar_dir, xml_notaria_root
from taxes.services.sunat_errors import recibo_needs_sunat_retry


def procesar_recibo_xml(recibo_id: int) -> dict:
    unsigned_path = generar_recibo_xml(recibo_id=recibo_id)
    signed_path = firmar_recibo_xml(recibo_id=recibo_id, unsigned_path=unsigned_path)
    result = {
        "generar": str(unsigned_path),
        "firmar": str(signed_path),
    }

    ctx = fetch_recibo_xml_context(recibo_id)
    if should_auto_enviar_sunat(ctx):
        sunat = enviar_recibo_sunat(
            recibo_id=recibo_id,
            ctx=ctx,
            signed_path=signed_path,
            raise_on_failure=False,
        )
        result["sunat"] = sunat
        if recibo_needs_sunat_retry(sunat):
            from taxes.services.sunat_outbox import enqueue_recibo_send

            enqueue_recibo_send(
                recibo_id=recibo_id,
                last_error=str(sunat.get("msj_sunat") or ""),
            )
    return result


__all__ = [
    "can_enviar_recibo_sunat",
    "consultar_ticket_baja",
    "consultar_ticket_resumen",
    "enviar_baja_sunat",
    "enviar_recibo_sunat",
    "enviar_resumen_sunat",
    "firmar_dir",
    "firmar_recibo_xml",
    "generar_dir",
    "generar_recibo_xml",
    "procesar_baja_sunat",
    "procesar_recibo_xml",
    "procesar_resumen_sunat",
    "should_auto_enviar_sunat",
    "xml_notaria_root",
]
