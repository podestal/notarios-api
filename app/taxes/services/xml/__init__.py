from .firmar import firmar_recibo_xml
from .generar import generar_recibo_xml
from .paths import firmar_dir, generar_dir, xml_notaria_root


def procesar_recibo_xml(recibo_id: int) -> dict:
    unsigned_path = generar_recibo_xml(recibo_id=recibo_id)
    signed_path = firmar_recibo_xml(recibo_id=recibo_id, unsigned_path=unsigned_path)
    return {
        "generar": str(unsigned_path),
        "firmar": str(signed_path),
    }


__all__ = [
    "firmar_dir",
    "firmar_recibo_xml",
    "generar_dir",
    "generar_recibo_xml",
    "procesar_recibo_xml",
    "xml_notaria_root",
]
