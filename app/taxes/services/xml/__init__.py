from .firmar import firmar_recibo_xml
from .generar import generar_recibo_xml
from .enviar import can_enviar_recibo_sunat, enviar_recibo_sunat, should_auto_enviar_sunat
from .context import fetch_recibo_xml_context
from .paths import firmar_dir, generar_dir, xml_notaria_root


def procesar_recibo_xml(recibo_id: int) -> dict:
    unsigned_path = generar_recibo_xml(recibo_id=recibo_id)
    signed_path = firmar_recibo_xml(recibo_id=recibo_id, unsigned_path=unsigned_path)
    result = {
        "generar": str(unsigned_path),
        "firmar": str(signed_path),
    }

    ctx = fetch_recibo_xml_context(recibo_id)
    if should_auto_enviar_sunat(ctx):
        result["sunat"] = enviar_recibo_sunat(
            recibo_id=recibo_id,
            ctx=ctx,
            signed_path=signed_path,
            raise_on_failure=True,
        )
    return result


__all__ = [
    "can_enviar_recibo_sunat",
    "enviar_recibo_sunat",
    "firmar_dir",
    "firmar_recibo_xml",
    "generar_dir",
    "generar_recibo_xml",
    "procesar_recibo_xml",
    "should_auto_enviar_sunat",
    "xml_notaria_root",
]
