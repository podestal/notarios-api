from typing import Any, Dict, List, Tuple

from uif.services.load_data import TIPO_INSTRUMENTO_MAP


def patrimonial_key(kardex: str, act_code: str) -> Tuple[str, str]:
    return (kardex, str(act_code).zfill(3))


def resolve_cxa_rows(entry) -> List[Any]:
    """Normalize map values that may be one CXA or a list (O+R same person)."""
    if entry is None:
        return []
    if isinstance(entry, (list, tuple)):
        return [row for row in entry if row is not None]
    return [entry]


def lookup_cxa_rows(
    contratantesxacto_map: Dict,
    kardex: str,
    act_code: str,
    idcontratante,
) -> List[Any]:
    act_padded = str(act_code).zfill(3)
    entry = contratantesxacto_map.get(f"{kardex}_{act_code}_{idcontratante}")
    if entry is None:
        entry = contratantesxacto_map.get(f"{kardex}_{act_padded}_{idcontratante}")
    return resolve_cxa_rows(entry)


def append_cxa_to_map(contratantesxacto_map: Dict, cxa) -> None:
    """Keep every role row for the same kardex/acto/contratante (e.g. O and R)."""
    key = f"{cxa.kardex}_{cxa.idtipoacto}_{cxa.idcontratante}"
    key_z = f"{cxa.kardex}_{str(cxa.idtipoacto).zfill(3)}_{cxa.idcontratante}"
    bucket = contratantesxacto_map.get(key)
    if bucket is None:
        bucket = contratantesxacto_map.get(key_z)
    if bucket is None:
        bucket = []
    else:
        bucket = resolve_cxa_rows(bucket)
    contratantesxacto_map[key] = bucket
    contratantesxacto_map[key_z] = bucket
    if cxa not in bucket:
        bucket.append(cxa)


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
