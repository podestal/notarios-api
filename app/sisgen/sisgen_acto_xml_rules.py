"""
Reglas SISGEN para bloques UIF/SUNAT en XML (cuantía, medios, origen fondos, renta).

Fuente: columnas de ``tiposdeacto`` en BD (misma tabla que alimenta el legado PHP).
No se usa lista fija de cod_ancert: si el acto no tiene código UIF/SUNAT ni flags S,
no se emiten esos bloques (p. ej. PODER 0604 con actouif vacío y mediospago/cuantia en N).
"""

from typing import Dict, Optional

_NEGATIVOS = frozenset({"N", "NO", "0", "-", "NINGUNO", "NONE"})


def _strip(value: Optional[str]) -> str:
    return (value or "").strip()


def tiposdeacto_flag_on(value: Optional[str]) -> bool:
    """``tiposdeacto`` mediospago / cuantia / origenfondo / impuestorenta: S o 1."""
    s = _strip(value).upper()
    if not s or s in _NEGATIVOS:
        return False
    return s in ("S", "1", "SI", "Y", "YES", "TRUE", "T")


def codigo_uif_o_sunat_presente(value: Optional[str]) -> bool:
    """Código UIF/SUNAT en catálogo (p. ej. 053, 010); vacío o N = no aplica."""
    s = _strip(value)
    if not s:
        return False
    if s.upper() in _NEGATIVOS:
        return False
    return True


def doc_requires_uif_sunat_xml(doc: Dict) -> bool:
    """
    ¿Emitir CuantiaOperacion, MediosPagos, OrigenFondos y renta en XML?

    Equivalente funcional a PHP ``validarUIFSUNAT == 1``, leyendo ``tiposdeacto``.
    """
    if codigo_uif_o_sunat_presente(doc.get("actouif")):
        return True
    if codigo_uif_o_sunat_presente(doc.get("actosunat")):
        return True
    for key in ("mediospago", "cuantia", "origenfondo", "impuestorenta"):
        if tiposdeacto_flag_on(doc.get(key)):
            return True
    return False


def doc_requires_medios_pago_xml(doc: Dict) -> bool:
    """Medios de pago: requiere acto UIF/SUNAT y flag mediospago S (o código UIF sin flag N)."""
    if not doc_requires_uif_sunat_xml(doc):
        return False
    mp = _strip(doc.get("mediospago"))
    if mp:
        return tiposdeacto_flag_on(mp)
    return codigo_uif_o_sunat_presente(doc.get("actouif")) or codigo_uif_o_sunat_presente(
        doc.get("actosunat")
    )


def doc_requires_cuantia_operacion_xml(doc: Dict) -> bool:
    """Cuantía de operación: flag cuantia S o acto con código UIF/SUNAT."""
    if tiposdeacto_flag_on(doc.get("cuantia")):
        return True
    return doc_requires_uif_sunat_xml(doc) and (
        codigo_uif_o_sunat_presente(doc.get("actouif"))
        or codigo_uif_o_sunat_presente(doc.get("actosunat"))
    )
