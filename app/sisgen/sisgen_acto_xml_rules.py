"""
Reglas SISGEN para bloques UIF/SUNAT en XML (cuantía, medios, origen fondos, renta).

Gate principal: PHP ``validarUIFSUNAT(cod_ancert)`` — lista fija de actos excluidos.
Cuando el acto no está en esa lista, se emiten CuantiaOperacion, MediosPagos (aunque
vacío), OrigenFondos y renta igual que el legado ``xml_kardex.php``.
"""

from typing import Dict, Optional

# PHP validarUIFSUNAT → actosNOUIFSUNAT
ACTOS_NO_UIF_SUNAT = frozenset(
    {
        "0229",
        "0511",
        "0601",
        "0602",
        "0603",
        "0604",
        "0605",
        "0606",
        "0607",
        "0608",
        "0701",
        "0703",
        "0704",
        "0705",
        "0706",
        "0806",
        "0810",
        "0907",
        "0908",
        "0910",
        "0912",
        "0913",
        "0914",
        "0915",
        "0916",
        "0917",
        "0919",
        "0920",
    }
)

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


def cod_ancert_requires_uif_sunat_xml(cod_ancert: Optional[str]) -> bool:
    """PHP ``validarUIFSUNAT``: 1 si cod_ancert no está en actosNOUIFSUNAT."""
    cod = _strip(cod_ancert)
    if not cod:
        return False
    return cod not in ACTOS_NO_UIF_SUNAT


def doc_requires_uif_sunat_xml(doc: Dict) -> bool:
    """
    ¿Emitir bloques UIF/SUNAT (cuantía, medios, origen fondos, renta)?

    Equivalente a PHP ``validarUIFSUNAT($kardcant['cod_ancert']) == 1``.
    """
    return cod_ancert_requires_uif_sunat_xml(doc.get("cod_ancert"))


def doc_requires_medios_pago_xml(doc: Dict) -> bool:
    """PHP: si ``validarUIFSUNAT``, siempre se abre ``<MediosPagos>`` (aunque vacío)."""
    return doc_requires_uif_sunat_xml(doc)


def doc_requires_cuantia_operacion_xml(doc: Dict) -> bool:
    """PHP: ``CuantiaOperacion`` bajo el mismo gate ``validarUIFSUNAT``."""
    return doc_requires_uif_sunat_xml(doc)
