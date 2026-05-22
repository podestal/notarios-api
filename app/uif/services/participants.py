"""
Patrimonial + participant (O/B) validation — uses ro_validation_by_act field 52.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from uif.services.constants import (
    ACTS_EXEMPT_BENEFICIARIO_AMOUNT,
    ACTS_EXEMPT_OTORGANTE_AMOUNT,
    AMOUNT_PARTICIPANT_ROLES,
    ROLE_BENEFICIARIO,
    ROLE_OTORGANTE,
)
from uif.services.errors import (
    CODE_ELEMENT_AMOUNT_BENEFICIARIO,
    CODE_ELEMENT_AMOUNT_OTORGANTE,
    ROW_TYPE_PARTICIPANT,
    build_ro_error,
)
from uif.services.keys import patrimonial_key
from uif.services.ro_validation_rules import (
    FIELD_MONTO_PARTICIPANTE,
    RoValidationRulesRepository,
    validation_code,
)

logger = logging.getLogger(__name__)


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_amount(value: Decimal) -> str:
    return format(_round2(value), "f")


class PatrimonialParticipantValidator:
    """RoClass generateData O/B monto rules + field 52 regex."""

    def __init__(self, rules: Optional[RoValidationRulesRepository] = None):
        self.rules = rules or RoValidationRulesRepository()
        self.rules.load()

    def validate(
        self,
        kardex: str,
        act_code: str,
        act_description: str,
        uif_code: str,
        id_kardex,
        patrimonial_map: Dict,
        contratantes_map: Dict,
        clientes_map: Dict,
        contratantesxacto_map: Dict,
    ) -> List[dict]:
        errors: List[dict] = []
        try:
            patrimonial = patrimonial_map.get(patrimonial_key(kardex, act_code))
            if not patrimonial:
                return errors

            uif_act = (uif_code or "").strip()
            rule_52 = self.rules.get(uif_act, FIELD_MONTO_PARTICIPANTE)
            contratantes = contratantes_map.get(kardex, [])
            act_code_padded = str(act_code).zfill(3)

            if patrimonial.idmon and str(patrimonial.idmon) not in ("", "0"):
                if not patrimonial.importetrans or patrimonial.importetrans == 0:
                    for contratante in contratantes:
                        cxa = self._get_cxa(
                            kardex, act_code, act_code_padded, contratante, contratantesxacto_map
                        )
                        if not cxa:
                            continue
                        role = (cxa.uif or "").strip().upper()
                        if role not in (ROLE_OTORGANTE, ROLE_BENEFICIARIO):
                            continue
                        nombre = self._nombre(
                            clientes_map.get(contratante.idcontratante), contratante
                        )
                        if clientes_map.get(contratante.idcontratante):
                            errors.append(
                                build_ro_error(
                                    id_kardex=id_kardex,
                                    kardex=kardex,
                                    act=act_description,
                                    codacto=act_code,
                                    uif_code=uif_act,
                                    error_type="currency_without_amount",
                                    error_description=(
                                        f"{nombre}, código de moneda no se debe informar sin montos"
                                    ),
                                    field_number=FIELD_MONTO_PARTICIPANTE,
                                    row_type=ROW_TYPE_PARTICIPANT,
                                    id_contratante=contratante.idcontratante,
                                    details_error=nombre,
                                    is_correctable=True,
                                    type_of_correction="MANUAL",
                                )
                            )

            if not patrimonial.importetrans or patrimonial.importetrans == 0:
                return errors

            monto_operacion = _round2(_to_decimal(patrimonial.importetrans))
            sum_o = Decimal("0")
            sum_b = Decimal("0")

            for contratante in contratantes:
                cxa = self._get_cxa(
                    kardex, act_code, act_code_padded, contratante, contratantesxacto_map
                )
                if not cxa:
                    continue

                role = (cxa.uif or "").strip().upper()
                if role not in AMOUNT_PARTICIPANT_ROLES:
                    continue

                nombre = self._nombre(clientes_map.get(contratante.idcontratante), contratante)
                monto = self._parse_monto(cxa.monto)
                monto_str = _format_amount(monto) if monto is not None else ""

                if rule_52 and role != "R":
                    if monto_str and validation_code(monto_str, rule_52.data_value):
                        errors.append(
                            build_ro_error(
                                id_kardex=id_kardex,
                                kardex=kardex,
                                act=act_description,
                                codacto=act_code,
                                uif_code=uif_act,
                                error_type="invalid_monto_participante",
                                error_description=(
                                    f"{nombre}: {self.rules.field_label(FIELD_MONTO_PARTICIPANTE)} inválido"
                                ),
                                field_number=FIELD_MONTO_PARTICIPANTE,
                                row_type=ROW_TYPE_PARTICIPANT,
                                id_contratante=contratante.idcontratante,
                                details_error=nombre,
                                detail_value=rule_52.detail_value or "",
                                is_correctable=True,
                                type_of_correction="MANUAL",
                            )
                        )

                if monto is None or monto == 0:
                    errors.append(
                        build_ro_error(
                            id_kardex=id_kardex,
                            kardex=kardex,
                            act=act_description,
                            codacto=act_code,
                            uif_code=uif_act,
                            error_type="missing_participant_amount",
                            error_description=f"{nombre} Monto por Participante",
                            field_number=FIELD_MONTO_PARTICIPANTE,
                            row_type=ROW_TYPE_PARTICIPANT,
                            id_contratante=contratante.idcontratante,
                            details_error=nombre,
                            is_correctable=True,
                            type_of_correction="MANUAL",
                        )
                    )
                    continue

                if role == ROLE_OTORGANTE:
                    sum_o += monto
                elif role == ROLE_BENEFICIARIO:
                    sum_b += monto

            if uif_act not in ACTS_EXEMPT_OTORGANTE_AMOUNT:
                if sum_o > 0 and _format_amount(sum_o) != _format_amount(monto_operacion):
                    errors.append(
                        build_ro_error(
                            id_kardex=id_kardex,
                            kardex=kardex,
                            act=act_description,
                            codacto=act_code,
                            uif_code=uif_act,
                            error_type="amount_mismatch",
                            error_description=(
                                "La suma de los montos de los contratantes otorgantes supera "
                                f"el monto total de la operacion: {_format_amount(monto_operacion)}"
                            ),
                            field_number=FIELD_MONTO_PARTICIPANTE,
                            code_element=CODE_ELEMENT_AMOUNT_OTORGANTE,
                            row_type=ROW_TYPE_PARTICIPANT,
                            is_correctable=True,
                            type_of_correction="MANUAL",
                        )
                    )

            if uif_act not in ACTS_EXEMPT_BENEFICIARIO_AMOUNT:
                if sum_b > 0 and _format_amount(sum_b) != _format_amount(monto_operacion):
                    errors.append(
                        build_ro_error(
                            id_kardex=id_kardex,
                            kardex=kardex,
                            act=act_description,
                            codacto=act_code,
                            uif_code=uif_act,
                            error_type="amount_mismatch",
                            error_description=(
                                "La suma de los montos de los contratantes beneficierios supera "
                                f"el monto total de la operacion: {_format_amount(monto_operacion)}"
                            ),
                            field_number=FIELD_MONTO_PARTICIPANTE,
                            code_element=CODE_ELEMENT_AMOUNT_BENEFICIARIO,
                            row_type=ROW_TYPE_PARTICIPANT,
                            is_correctable=True,
                            type_of_correction="MANUAL",
                        )
                    )

        except Exception as exc:
            logger.warning("Error validating patrimonial data for kardex %s: %s", kardex, exc)

        return errors

    @staticmethod
    def _nombre(cliente, contratante) -> str:
        if not cliente:
            return f"Contratante {contratante.idcontratante}"
        if (cliente.tipper or "N").upper() == "J":
            return (cliente.razonsocial or "").strip() or f"Contratante {contratante.idcontratante}"
        parts = []
        for attr in ("apepat", "apemat", "prinom", "segnom"):
            val = getattr(cliente, attr, None)
            if val is not None and isinstance(val, str) and val.strip():
                parts.append(val.strip())
        name = " ".join(parts).strip()
        nombre = getattr(cliente, "nombre", None)
        if not name and nombre and isinstance(nombre, str):
            name = nombre.strip()
        return name or f"Contratante {contratante.idcontratante}"

    @staticmethod
    def _get_cxa(kardex, act_code, act_code_padded, contratante, contratantesxacto_map):
        return contratantesxacto_map.get(
            f"{kardex}_{act_code}_{contratante.idcontratante}"
        ) or contratantesxacto_map.get(
            f"{kardex}_{act_code_padded}_{contratante.idcontratante}"
        )

    @staticmethod
    def _parse_monto(value) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return _round2(_to_decimal(value))
        except Exception:
            return None
