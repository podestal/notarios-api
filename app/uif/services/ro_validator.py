"""
Full RO validation for an eligible staged row (Phase 3 + complementaria tipo C).
"""

from datetime import date
from typing import Dict, List, Optional, Tuple

from uif.services.errors import group_errors_by_kardex
from uif.services.keys import patrimonial_key
from uif.services.operation_validator import RoOperationValidator
from uif.services.participant_fields_validator import ParticipantFieldsValidator
from uif.services.participants import PatrimonialParticipantValidator
from uif.services.ro_validation_rules import RoValidationRulesRepository
from uif.services.staging import RoStagedRecord


class RoEligibleRowValidator:
    """Operation + participant validators driven by ro_validation_by_act."""

    def __init__(self, rules: Optional[RoValidationRulesRepository] = None):
        self.rules = rules or RoValidationRulesRepository()
        self.rules.load()
        self.operation_validator = RoOperationValidator(self.rules)
        self.participant_fields_validator = ParticipantFieldsValidator(self.rules)
        self.participant_validator = PatrimonialParticipantValidator(self.rules)

    def validate_row(
        self,
        staged: RoStagedRecord,
        act_description: str,
        patrimonial_map: Dict,
        contratantes_map: Dict,
        clientes_map: Dict,
        contratantesxacto_map: Dict,
        detalle_medio_pago_map: Dict,
        fpago_codigo_map: Dict[str, str],
        range_start: Optional[date] = None,
        range_end: Optional[date] = None,
    ) -> List[dict]:
        patrimonial = patrimonial_map.get(patrimonial_key(staged.kardex, staged.cod_acto))
        detalle_rows = detalle_medio_pago_map.get(staged.kardex, [])

        errors: List[dict] = []
        errors.extend(
            self.operation_validator.validate(
                staged=staged,
                act_description=act_description,
                patrimonial=patrimonial,
                detalle_medio_pago_rows=detalle_rows,
                fpago_codigo_map=fpago_codigo_map,
            )
        )
        errors.extend(
            self.participant_fields_validator.validate(
                staged=staged,
                act_description=act_description,
                contratantes_map=contratantes_map,
                clientes_map=clientes_map,
                contratantesxacto_map=contratantesxacto_map,
                detalle_medio_pago_rows=detalle_rows,
                range_start=range_start,
                range_end=range_end,
            )
        )
        errors.extend(
            self.participant_validator.validate(
                staged.kardex,
                staged.cod_acto,
                act_description,
                staged.uif_code,
                staged.id_kardex,
                patrimonial_map,
                contratantes_map,
                clientes_map,
                contratantesxacto_map,
            )
        )
        return errors

    @staticmethod
    def summarize_errors(errors: List[dict]) -> Tuple[Dict[str, int], Dict[str, list]]:
        breakdown: Dict[str, int] = {}
        for err in errors:
            et = err.get("error_type") or "unknown"
            breakdown[et] = breakdown.get(et, 0) + 1
        return breakdown, group_errors_by_kardex(errors)
