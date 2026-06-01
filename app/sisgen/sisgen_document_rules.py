"""
Validación de documentos SISGEN (paridad xml_kardex.php ValidarDocumentoJuridica / Natural).
"""

from typing import Tuple


def normalize_tipo_doc_cod(tipo: str) -> str:
    s = (tipo or "").strip()
    if not s:
        return ""
    if s.isdigit():
        return str(int(s)).zfill(2)
    return s.upper()


def validar_documento_juridica(
    tipo: str, documento: str, tipo_instrumento: str
) -> Tuple[int, str, str]:
    """
    PHP ValidarDocumentoJuridica($tipo, $documento, $tipoInstrumento).

    Returns (err, errormensaje, tipo_resuelto). err=1 si hay error.
    Tipos 10 y 15 no exigen número de documento; 08 exige RUC (11 dígitos).
    """
    err = 0
    msg = ""
    tipo = normalize_tipo_doc_cod(tipo)
    documento = (documento or "").strip()
    ti = str(tipo_instrumento or "").strip()

    if ti == "2":
        return 0, "", tipo

    if tipo == "":
        if documento == "":
            tipo = "10"
        else:
            return 1, "Falta el tipo de documento", tipo
    elif documento == "":
        if tipo not in ("10", "15"):
            return 1, "Falta el numero de documento", tipo
    elif tipo != "08":
        if len(documento) == 11 and documento.isdigit():
            tipo = "08"
        else:
            return 1, "Tipo de documento no corresponde", tipo

    return err, msg, tipo


def juridica_requiere_formato_ruc(tipo_resuelto: str) -> bool:
    return normalize_tipo_doc_cod(tipo_resuelto) == "08"
