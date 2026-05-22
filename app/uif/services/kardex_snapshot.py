"""
Ad-hoc UIF validation for individual kardex numbers (SISGEN document search).
Uses the same RoEligibleRowValidator as the dashboard — no duplicate logic.
"""

import logging
from typing import Dict, List

from notaria import models
from uif.services.dashboard_service import UifDashboardService
from uif.services.load_data import _parse_act_codes, _stage_kardex_row
from uif.services.ro_validator import RoEligibleRowValidator

logger = logging.getLogger(__name__)

_EMPTY_RESULT = {
    "has_uif_errors": False,
    "uif_errors": [],
    "uif_observations": [],
    "patrimonial_data": {},
}


def bulk_validate_kardex_numbers(kardex_numbers: List[str]) -> Dict[str, Dict]:
    numbers = [str(k).strip() for k in kardex_numbers if k and str(k).strip()]
    return {k: validate_kardex_number(k) for k in numbers}


def validate_kardex_number(kardex_number: str) -> Dict:
    """Shape consumed by SISGEN document search (`uif_validation` block)."""
    key = str(kardex_number or "").strip()
    if not key:
        return dict(_EMPTY_RESULT)

    try:
        kardex = models.Kardex.objects.filter(kardex=key).first()
        if not kardex:
            return dict(_EMPTY_RESULT)

        act_codes = _parse_act_codes(kardex.codactos or "")
        tipos_uif = {
            t.idtipoacto: t
            for t in models.Tiposdeacto.objects.filter(
                idtipoacto__in=act_codes, actouif__isnull=False
            ).exclude(actouif="")
        }
        if not tipos_uif:
            return dict(_EMPTY_RESULT)

        dashboard = UifDashboardService()
        (
            patrimonial_map,
            contratantes_map,
            clientes_map,
            contratantesxacto_map,
            detalle_medio_pago_map,
            fpago_codigo_map,
        ) = dashboard._bulk_fetch_related([key], list(tipos_uif.keys()))

        validator = RoEligibleRowValidator()
        uif_errors: List[dict] = []
        patrimonial_data: Dict[str, dict] = {}

        for cod_acto in act_codes:
            tipo_acto = tipos_uif.get(cod_acto)
            if not tipo_acto:
                continue
            staged = _stage_kardex_row(kardex, cod_acto, tipo_acto, tipo="I")
            act_description = (
                tipo_acto.desacto if tipo_acto and tipo_acto.desacto else f"Acto {cod_acto}"
            )
            row_errors = validator.validate_row(
                staged,
                act_description,
                patrimonial_map,
                contratantes_map,
                clientes_map,
                contratantesxacto_map,
                detalle_medio_pago_map,
                fpago_codigo_map,
            )
            if row_errors:
                uif_errors.extend(row_errors)
            else:
                summary = dashboard._get_patrimonial_summary(
                    key, cod_acto, patrimonial_map
                )
                patrimonial_data[cod_acto] = summary

        return {
            "has_uif_errors": len(uif_errors) > 0,
            "uif_errors": uif_errors,
            "uif_observations": [],
            "patrimonial_data": patrimonial_data,
        }
    except Exception as exc:
        logger.warning("UIF snapshot validation failed for %s: %s", key, exc)
        return {
            "has_uif_errors": True,
            "uif_errors": [
                {
                    "error_type": "validation_error",
                    "error_description": f"Error validando UIF: {exc}",
                }
            ],
            "uif_observations": [],
            "patrimonial_data": {},
        }
