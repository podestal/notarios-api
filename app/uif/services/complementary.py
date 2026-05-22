"""
RoClass informacion complementaria (tipo envio C) helpers.
"""

from datetime import date, datetime
from typing import List, Optional, Tuple

from notaria.models import Detallemediopago, Kardex


def parse_fecha_firma(value) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def escritura_before_range(kardex_number: str, range_start: date) -> bool:
    """PHP: kardex.fechaescritura < initialDate and not empty."""
    kardex = Kardex.objects.filter(kardex=kardex_number).only("fechaescritura").first()
    if not kardex or not kardex.fechaescritura:
        return False
    fe = kardex.fechaescritura
    if hasattr(fe, "year"):
        return fe < range_start
    parsed = parse_fecha_firma(fe)
    return parsed is not None and parsed < range_start


def firma_in_report_range(firma_value, start_date: date, end_date: date) -> bool:
    firma = parse_fecha_firma(firma_value)
    return firma is not None and start_date <= firma <= end_date


def group_medios_for_act(
    kardex: str, cod_acto: str, detalle_rows: List[Detallemediopago]
) -> Tuple[List[dict], str]:
    """Returns (grouped medios, tipo_acto for participant filter)."""
    act_variants = {cod_acto, str(cod_acto).zfill(3), str(cod_acto).lstrip("0")}
    grouped: dict = {}
    tipo_acto = cod_acto
    for det in detalle_rows:
        if str(det.tipacto or "") not in act_variants:
            continue
        key = (det.codmepag, det.tipacto)
        if key not in grouped:
            grouped[key] = {
                "tipacto": det.tipacto,
                "codmepag": det.codmepag,
            }
        tipo_acto = str(det.tipacto or cod_acto)
    return list(grouped.values()), tipo_acto


def has_medios_for_act(kardex: str, cod_acto: str, detalle_rows: List) -> bool:
    medios, _ = group_medios_for_act(kardex, cod_acto, detalle_rows)
    return bool(medios)
