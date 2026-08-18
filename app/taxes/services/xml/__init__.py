import logging
from pathlib import Path

from rest_framework.exceptions import NotFound

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
from .paths import firmar_dir, firmar_path, generar_dir, xml_notaria_root
from taxes.services.sunat_errors import recibo_needs_sunat_retry

logger = logging.getLogger(__name__)


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

            try:
                enqueue_recibo_send(
                    recibo_id=recibo_id,
                    last_error=str(sunat.get("msj_sunat") or ""),
                )
            except Exception:
                # Recibo + XML already done; missing outbox table must not 500 the client.
                logger.exception(
                    "Failed to enqueue SUNAT retry for recibo_id=%s "
                    "(run: python manage.py migrate taxes --database=postgres)",
                    recibo_id,
                )
    return result


def resolve_recibo_signed_xml_path(recibo_id: int) -> tuple[Path, str]:
    """Signed XML in xml_notaria/firmar and a download filename (serie-numero.xml)."""
    ctx = fetch_recibo_xml_context(recibo_id)
    path = firmar_path(
        ruc=ctx.ruc_emisor,
        codigo_comprobante=ctx.codigo_comprobante,
        serie=ctx.serie,
        numero=ctx.numero,
    )
    if not path.is_file():
        raise NotFound(
            "Signed XML not found. Create the comprobante first "
            "(POST /taxes/recibos/) so xml_notaria/firmar is populated."
        )
    filename = f"{ctx.serie}-{ctx.numero_padded}.xml"
    return path, filename


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
    "resolve_recibo_signed_xml_path",
    "should_auto_enviar_sunat",
    "xml_notaria_root",
]
