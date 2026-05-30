"""
Load and apply rules from `ro_validation_by_act` (MySQL REGEXP parity).
"""

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from notaria.constants import OPORTUNIDADES_PAGO
from uif.models import RoDataField, RoValidationByAct

# fkDataField / numberOfData aliases used in RoClass generateData SQL.
FIELD_FORMA_PAGO = 46
FIELD_OPORTUNIDAD_PAGO = 47
FIELD_MEDIO_PAGO_CODIGO = 44
FIELD_MONTO_OPERACION = 51
FIELD_MONTO_PARTICIPANTE = 52
FIELD_MONTO_TIPO_FONDO = 53
FIELD_NUMERO_ESCRITURA = 5
FIELD_REPRESENTANTE = 13
FIELD_PERSONA_OPERACION = 14
FIELD_PERSONA_AFAVOR = 15
FIELD_PERSONA_QUE_REPRESENTA = 16
FIELD_TIPO_REPRESENTACION = 17
FIELD_CONDICION_RESIDENCIA = 18
FIELD_TIPO_PERSONA = 19
FIELD_TIPO_DOCUMENTO = 20
FIELD_NUMERO_DOCUMENTO = 21
FIELD_NUMERO_RUC = 22
FIELD_APELLIDO_RAZON = 23
FIELD_APELLIDO_MATERNO = 24
FIELD_NOMBRES = 25
FIELD_NACIONALIDAD = 26
FIELD_FECHA_NACIMIENTO = 27
FIELD_ESTADO_CIVIL = 28
FIELD_PROFESION = 29
FIELD_OBJETO_SOCIAL = 30
FIELD_CIIU = 31
FIELD_CARGO = 32
FIELD_ZONA_REGISTRAL = 33
FIELD_PARTIDA_REGISTRAL = 34
FIELD_DIRECCION = 35
FIELD_DEPARTAMENTO = 36
FIELD_PROVINCIA = 37
FIELD_DISTRITO = 38
FIELD_FECHA_FIRMA = 10
FIELD_PARTICIPACION_CONYUGE = 40
FIELD_APELLIDO_PATERNO_CONYUGE = 41
FIELD_APELLIDO_MATERNO_CONYUGE = 42
FIELD_NOMBRES_CONYUGE = 43


class RoValidationRulesRepository:
    """In-memory index of ro_validation_by_act (+ optional field labels)."""

    def __init__(self):
        self._rules: Dict[Tuple[str, int], RoValidationByAct] = {}
        self._field_labels: Dict[int, str] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        for rule in RoValidationByAct.objects.all():
            if rule.code_act and rule.fk_data_field is not None:
                self._rules[(rule.code_act.strip(), int(rule.fk_data_field))] = rule
        for field in RoDataField.objects.all():
            if field.number_of_data is not None:
                self._field_labels[int(field.number_of_data)] = field.column_description or ""
        self._loaded = True

    def get(self, uif_code: str, field_number: int) -> Optional[RoValidationByAct]:
        self.load()
        return self._rules.get(((uif_code or "").strip(), field_number))

    def field_label(self, field_number: int) -> str:
        self.load()
        return self._field_labels.get(field_number, f"Campo {field_number}")

    def detail_value(self, uif_code: str, field_number: int) -> str:
        rule = self.get(uif_code, field_number)
        return (rule.detail_value or "") if rule else ""


def matches_mysql_regexp(value: str, pattern: Optional[str]) -> bool:
    """True when value matches MySQL REGEXP pattern (empty pattern => match all)."""
    if not pattern or not str(pattern).strip():
        return True
    text = "" if value is None else str(value).strip()
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return False


def validation_code(value: str, pattern: Optional[str]) -> int:
    """0 = OK, else returns field error (PHP: REGEXP != 0 THEN 0 ELSE field)."""
    return 0 if matches_mysql_regexp(value, pattern) else 1


def oportunidad_pago_validation_value(idoppago) -> str:
    """
    Value checked against ro_validation_by_act field 47 (PHP generateData SQL).

    RoClass uses: IF(patrimonial.idoppago = '', 'V', patrimonial.idoppago).
    Catalog id 10 is ``VACIO`` (``codoppago`` empty) — same semantics as empty → ``V``.
    """
    raw = "" if idoppago is None else str(idoppago).strip()
    if raw == "":
        return "V"
    try:
        meta = OPORTUNIDADES_PAGO.get(int(raw))
    except (TypeError, ValueError):
        return raw
    if meta and not str(meta.get("codoppago") or "").strip():
        return "V"
    cod = str(meta.get("codoppago") or "").strip()
    return cod if cod else raw


def medio_pago_uif_validation_value(uif_code) -> str:
    """
    Value checked against ro_validation_by_act field 44 (PHP generateData SQL).

    RoClass uses: IF(mediospago.uif = '', 'V', mediospago.uif).
    """
    text = "" if uif_code is None else str(uif_code).strip()
    return "V" if text == "" else text


def group_detalle_medio_importe_sums(rows) -> Dict[Tuple, dict]:
    """
    PHP medio de pago query: GROUP BY detallemediopago.codmepag, tipacto.
    """
    groups: Dict[Tuple, dict] = {}
    for row in rows:
        key = (row.codmepag, row.tipacto)
        if key not in groups:
            groups[key] = {"has_importemp": False, "total": None}
        imp = row.importemp
        if imp is None or str(imp).strip() == "":
            continue
        groups[key]["has_importemp"] = True
        current = groups[key]["total"]
        amount = Decimal(str(imp))
        groups[key]["total"] = amount if current is None else current + amount
    return groups


def monto_tipo_fondo_validation_value(total, *, has_importemp: bool) -> str:
    """
    Value checked against ro_validation_by_act field 53 (PHP generateData SQL).

    RoClass uses: IF(SUM(detallemediopago.importemp) IS NULL, 'V', SUM(...)).
    """
    if not has_importemp or total is None:
        return "V"
    d = Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(d, "f")

