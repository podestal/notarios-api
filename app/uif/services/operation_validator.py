"""
Operation-level RoClass validations (patrimonial + detallemediopago).

Parity rule: errors must match RoClass / `ro_validation_by_act`; do not invent
required-field rules that PHP does not surface in generateData.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from notaria import models
from uif.models import Mediospago
from uif.services.errors import (
    CODE_ELEMENT_ESCRITURA,
    CODE_ELEMENT_MISSING_PAYMENT_ROWS,
    ROW_TYPE_OPERATION,
    build_ro_error,
)
from uif.services.keys import patrimonial_key
from uif.services.ro_validation_rules import (
    FIELD_FORMA_PAGO,
    FIELD_MEDIO_PAGO_CODIGO,
    FIELD_MONTO_OPERACION,
    FIELD_MONTO_TIPO_FONDO,
    FIELD_NUMERO_ESCRITURA,
    FIELD_OPORTUNIDAD_PAGO,
    RoValidationRulesRepository,
    matches_mysql_regexp,
    oportunidad_pago_validation_value,
    validation_code,
)
from uif.models import FpagoUif

logger = logging.getLogger(__name__)


def _format_decimal(value) -> str:
    if value is None or value == "":
        return "0.00"
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(d, "f")


class RoOperationValidator:
    """Validates forma pago, oportunidad, montos, medios de pago, escritura."""

    def __init__(self, rules: Optional[RoValidationRulesRepository] = None):
        self.rules = rules or RoValidationRulesRepository()
        self.rules.load()

    def validate(
        self,
        *,
        staged,
        act_description: str,
        patrimonial,
        detalle_medio_pago_rows: List,
        fpago_codigo_map: Dict[str, str],
    ) -> List[dict]:
        errors: List[dict] = []
        uif_code = (staged.uif_code or "").strip()
        kardex = staged.kardex
        id_kardex = staged.id_kardex
        cod_acto = staged.cod_acto

        errors.extend(
            self._validate_escritura(staged, act_description, uif_code, cod_acto)
        )
        if str(getattr(staged, "tipo", "I")) == "I":
            errors.extend(
                self._validate_conclusion(staged, act_description, uif_code, cod_acto)
            )

        if patrimonial is None:
            errors.append(
                build_ro_error(
                    id_kardex=id_kardex,
                    kardex=kardex,
                    act=act_description,
                    codacto=cod_acto,
                    uif_code=uif_code,
                    error_type="missing_patrimonial_data",
                    error_description="Datos patrimoniales no encontrados para el acto",
                    field_number=FIELD_MONTO_OPERACION,
                    row_type=ROW_TYPE_OPERATION,
                    is_correctable=False,
                    detail_value=self.rules.detail_value(uif_code, FIELD_MONTO_OPERACION),
                )
            )
            return errors

        errors.extend(
            self._validate_patrimonial_fields(
                patrimonial, staged, act_description, uif_code, fpago_codigo_map
            )
        )
        # PHP generateData (tipoEnvio == 'I'): if detallemediopago query returns no rows,
        # always emit codeElement 590 — independent of patrimonial.exhibiomp.
        errors.extend(
            self._validate_medios_pago(
                patrimonial, staged, act_description, uif_code, detalle_medio_pago_rows
            )
        )
        return errors

    def _validate_escritura(self, staged, act_description, uif_code, cod_acto) -> List[dict]:
        num = staged.numero_escritura
        text = "" if num is None else str(num).strip()
        if text and text != " " and int(text or "0") != 0:
            return []
        detail = self.rules.detail_value(uif_code, FIELD_NUMERO_ESCRITURA)
        return [
            build_ro_error(
                id_kardex=staged.id_kardex,
                kardex=staged.kardex,
                act=act_description,
                codacto=cod_acto,
                uif_code=uif_code,
                error_type="missing_escritura_number",
                error_description="Número de escritura faltante",
                field_number=FIELD_NUMERO_ESCRITURA,
                code_element=CODE_ELEMENT_ESCRITURA,
                row_type=ROW_TYPE_OPERATION,
                is_correctable=False,
                detail_value=detail,
            )
        ]

    def _validate_conclusion(self, staged, act_description, uif_code, cod_acto) -> List[dict]:
        if staged.fecha_conclusion:
            return []
        return [
            build_ro_error(
                id_kardex=staged.id_kardex,
                kardex=staged.kardex,
                act=act_description,
                codacto=cod_acto,
                uif_code=uif_code,
                error_type="missing_conclusion_date",
                error_description="Fecha de conclusión faltante",
                field_number=0,
                row_type=ROW_TYPE_OPERATION,
                is_correctable=False,
            )
        ]

    def _validate_patrimonial_fields(
        self, patrimonial, staged, act_description, uif_code, fpago_codigo_map
    ) -> List[dict]:
        errors: List[dict] = []
        kardex = staged.kardex

        rule_fpago = self.rules.get(uif_code, FIELD_FORMA_PAGO)
        if rule_fpago:
            codigo_fpago = fpago_codigo_map.get(str(patrimonial.fpago or "").strip(), "")
            if validation_code(codigo_fpago, rule_fpago.data_value):
                errors.append(
                    build_ro_error(
                        id_kardex=staged.id_kardex,
                        kardex=kardex,
                        act=act_description,
                        codacto=staged.cod_acto,
                        uif_code=uif_code,
                        error_type="invalid_forma_pago",
                        error_description=(
                            f"Forma de pago inválida para el acto UIF {uif_code}. "
                            f"Valores permitidos: {rule_fpago.detail_value or rule_fpago.data_value}"
                        ),
                        field_number=FIELD_FORMA_PAGO,
                        row_type=ROW_TYPE_OPERATION,
                        is_correctable=True,
                        type_of_correction="MANUAL",
                        detail_value=rule_fpago.detail_value or "",
                    )
                )

        rule_opp = self.rules.get(uif_code, FIELD_OPORTUNIDAD_PAGO)
        if rule_opp:
            opp_check = oportunidad_pago_validation_value(patrimonial.idoppago)
            if validation_code(opp_check, rule_opp.data_value):
                errors.append(
                    build_ro_error(
                        id_kardex=staged.id_kardex,
                        kardex=kardex,
                        act=act_description,
                        codacto=staged.cod_acto,
                        uif_code=uif_code,
                        error_type="invalid_oportunidad_pago",
                        error_description=(
                            f"Oportunidad de pago inválida. "
                            f"Valores permitidos: {rule_opp.detail_value or rule_opp.data_value}"
                        ),
                        field_number=FIELD_OPORTUNIDAD_PAGO,
                        row_type=ROW_TYPE_OPERATION,
                        is_correctable=True,
                        type_of_correction="MANUAL",
                        detail_value=rule_opp.detail_value or "",
                    )
                )
            opp_raw = str(patrimonial.idoppago or "").strip()
            if opp_raw == "99" and not (patrimonial.des_idoppago or "").strip():
                errors.append(
                    build_ro_error(
                        id_kardex=staged.id_kardex,
                        kardex=kardex,
                        act=act_description,
                        codacto=staged.cod_acto,
                        uif_code=uif_code,
                        error_type="missing_oportunidad_descripcion",
                        error_description="Descripción de oportunidad de pago requerida (código 99)",
                        field_number=FIELD_OPORTUNIDAD_PAGO,
                        row_type=ROW_TYPE_OPERATION,
                        is_correctable=True,
                        type_of_correction="MANUAL",
                    )
                )

        rule_monto = self.rules.get(uif_code, FIELD_MONTO_OPERACION)
        idmon = str(patrimonial.idmon or "").strip()
        importe = patrimonial.importetrans
        importe_str = _format_decimal(importe) if importe not in (None, "", 0) else "0.00"

        if idmon not in ("", "0") and (not importe or importe == 0):
            errors.append(
                build_ro_error(
                    id_kardex=staged.id_kardex,
                    kardex=kardex,
                    act=act_description,
                    codacto=staged.cod_acto,
                    uif_code=uif_code,
                    error_type="currency_without_amount",
                    error_description="Código de moneda informado sin monto total de operación",
                    field_number=FIELD_MONTO_OPERACION,
                    row_type=ROW_TYPE_OPERATION,
                    detail_value=self.rules.detail_value(uif_code, FIELD_MONTO_OPERACION),
                )
            )
        elif rule_monto and importe_str not in ("", "0.00"):
            if validation_code(importe_str, rule_monto.data_value):
                errors.append(
                    build_ro_error(
                        id_kardex=staged.id_kardex,
                        kardex=kardex,
                        act=act_description,
                        codacto=staged.cod_acto,
                        uif_code=uif_code,
                        error_type="invalid_monto_operacion",
                        error_description=self.rules.field_label(FIELD_MONTO_OPERACION)
                        + " inválido",
                        field_number=FIELD_MONTO_OPERACION,
                        row_type=ROW_TYPE_OPERATION,
                        detail_value=rule_monto.detail_value or "",
                    )
                )

        return errors

    def _validate_medios_pago(
        self, patrimonial, staged, act_description, uif_code, detalle_rows
    ) -> List[dict]:
        del patrimonial
        # Complementary (tipo C) uses a different generateData branch — no 590 there.
        if str(getattr(staged, "tipo", "I")) != "I":
            return []

        errors: List[dict] = []
        act_code = str(staged.cod_acto).zfill(3)
        rows = [
            r
            for r in detalle_rows
            if r.kardex == staged.kardex
            and str(r.tipacto or "").zfill(3) == act_code
        ]

        if not rows:
            return [
                build_ro_error(
                    id_kardex=staged.id_kardex,
                    kardex=staged.kardex,
                    act=act_description,
                    codacto=staged.cod_acto,
                    uif_code=uif_code,
                    error_type="missing_medio_pago_rows",
                    error_description="El kardex no tiene fila de T. de Pago/T. de Fondo",
                    field_number=FIELD_MONTO_TIPO_FONDO,
                    code_element=CODE_ELEMENT_MISSING_PAYMENT_ROWS,
                    row_type=ROW_TYPE_OPERATION,
                    is_correctable=False,
                )
            ]

        rule_sum = self.rules.get(uif_code, FIELD_MONTO_TIPO_FONDO)
        rule_codigo = self.rules.get(uif_code, FIELD_MEDIO_PAGO_CODIGO)

        total = Decimal("0")
        for row in rows:
            if row.importemp:
                total += Decimal(str(row.importemp))

        sum_str = _format_decimal(total)
        if rule_sum and validation_code(sum_str, rule_sum.data_value):
            errors.append(
                build_ro_error(
                    id_kardex=staged.id_kardex,
                    kardex=staged.kardex,
                    act=act_description,
                    codacto=staged.cod_acto,
                    uif_code=uif_code,
                    error_type="invalid_monto_tipo_fondo",
                    error_description=(
                        "Monto total de tipo(s) de fondo inválido o no coincide con detalle de pago"
                    ),
                    field_number=FIELD_MONTO_TIPO_FONDO,
                    row_type=ROW_TYPE_OPERATION,
                    detail_value=rule_sum.detail_value or "",
                )
            )

        if rule_codigo:
            for row in rows:
                codigo_fondo = self._resolve_medio_pago_uif(row)
                if validation_code(codigo_fondo, rule_codigo.data_value):
                    errors.append(
                        build_ro_error(
                            id_kardex=staged.id_kardex,
                            kardex=staged.kardex,
                            act=act_description,
                            codacto=staged.cod_acto,
                            uif_code=uif_code,
                            error_type="invalid_medio_pago_codigo",
                            error_description=(
                                f"Código de medio de pago inválido ({codigo_fondo or 'vacío'})"
                            ),
                            field_number=FIELD_MEDIO_PAGO_CODIGO,
                            row_type=ROW_TYPE_OPERATION,
                            detail_value=rule_codigo.detail_value or "",
                        )
                    )

        return errors

    @staticmethod
    def _resolve_medio_pago_uif(detalle_row) -> str:
        codmepag = detalle_row.codmepag
        if codmepag is None:
            return ""
        try:
            medio = Mediospago.objects.filter(codmepag=codmepag).first()
            return (medio.uif or "") if medio else ""
        except Exception:
            return ""
