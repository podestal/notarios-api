from typing import Any, Dict, Tuple

from uif.services.load_data import TIPO_INSTRUMENTO_MAP


def patrimonial_key(kardex: str, act_code: str) -> Tuple[str, str]:
    return (kardex, str(act_code).zfill(3))


def normalize_act_code(cod_acto: str) -> str:
    """SUNAT/PHP act codes are 3-digit strings (codactos slices)."""
    text = str(cod_acto or "").strip()
    if not text:
        return ""
    return text.zfill(3)[:3]


def resolve_instrumento_letter(ro: Dict[str, Any]) -> str:
    """
    RoClass IPNP — single letter E|T|G. Never use tipo envio (I/C) or idtipkar digits.
    """
    ti = str(ro.get("tipo_instrumento") or "").strip().upper()
    if ti in TIPO_INSTRUMENTO_MAP.values():
        return ti
    if ti and ti[0] in TIPO_INSTRUMENTO_MAP.values():
        return ti[0]
    try:
        idtipkar = int(ro.get("idtipkar") or 0)
    except (TypeError, ValueError):
        return ""
    return TIPO_INSTRUMENTO_MAP.get(idtipkar, "")
