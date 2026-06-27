"""
Ad-hoc UIF validation for individual kardex numbers (SISGEN document search).
Uses the same RoEligibleRowValidator as the dashboard — no duplicate logic.
"""

import logging
from typing import Dict, List, Optional

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


def bulk_count_uif_errors(
    kardex_numbers: List[str],
    *,
    kardex_by_key: Optional[Dict[str, models.Kardex]] = None,
    tipo_by_act: Optional[Dict[str, models.Tiposdeacto]] = None,
) -> Dict[str, int]:
    """Error counts only — skips patrimonial summaries (faster than full validation)."""
    numbers = [str(k).strip() for k in kardex_numbers if k and str(k).strip()]
    if not numbers:
        return {}

    if kardex_by_key is None:
        kardex_by_key = {
            row.kardex: row for row in models.Kardex.objects.filter(kardex__in=numbers)
        }

    kardex_act_codes: Dict[str, List[str]] = {}
    all_act_codes: set = set()
    for key in numbers:
        kardex = kardex_by_key.get(key)
        if not kardex:
            continue
        act_codes = _parse_act_codes(kardex.codactos or "")
        kardex_act_codes[key] = act_codes
        all_act_codes.update(act_codes)

    if not all_act_codes:
        return {key: 0 for key in numbers}

    if tipo_by_act is None:
        tipos_uif = {
            t.idtipoacto: t
            for t in models.Tiposdeacto.objects.filter(
                idtipoacto__in=all_act_codes, actouif__isnull=False
            ).exclude(actouif="")
        }
    else:
        tipos_uif = {
            str(k): t
            for k, t in tipo_by_act.items()
            if t.actouif and str(t.actouif).strip()
        }
    if not tipos_uif:
        return {key: 0 for key in numbers}

    dashboard = UifDashboardService()
    (
        patrimonial_map,
        contratantes_map,
        clientes_map,
        contratantesxacto_map,
        detalle_medio_pago_map,
        fpago_codigo_map,
    ) = dashboard._bulk_fetch_related(numbers, list(tipos_uif.keys()))

    validator = RoEligibleRowValidator()
    out: Dict[str, int] = {}

    for key in numbers:
        kardex = kardex_by_key.get(key)
        if not kardex:
            out[key] = 0
            continue

        act_codes = kardex_act_codes.get(key, [])
        if not any(str(cod) in tipos_uif for cod in act_codes):
            out[key] = 0
            continue

        try:
            error_count = 0
            for cod_acto in act_codes:
                tipo_acto = tipos_uif.get(str(cod_acto))
                if not tipo_acto:
                    continue
                staged = _stage_kardex_row(kardex, cod_acto, tipo_acto, tipo="I")
                act_description = (
                    tipo_acto.desacto
                    if tipo_acto and tipo_acto.desacto
                    else f"Acto {cod_acto}"
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
                error_count += len(row_errors)
            out[key] = error_count
        except Exception as exc:
            logger.warning("UIF count validation failed for %s: %s", key, exc)
            out[key] = 1

    return out


def bulk_validate_kardex_numbers(kardex_numbers: List[str]) -> Dict[str, Dict]:
    numbers = [str(k).strip() for k in kardex_numbers if k and str(k).strip()]
    if not numbers:
        return {}

    kardex_by_key = {
        row.kardex: row for row in models.Kardex.objects.filter(kardex__in=numbers)
    }

    kardex_act_codes: Dict[str, List[str]] = {}
    all_act_codes: set = set()
    for key in numbers:
        kardex = kardex_by_key.get(key)
        if not kardex:
            continue
        act_codes = _parse_act_codes(kardex.codactos or "")
        kardex_act_codes[key] = act_codes
        all_act_codes.update(act_codes)

    if not all_act_codes:
        return {key: dict(_EMPTY_RESULT) for key in numbers}

    tipos_uif = {
        t.idtipoacto: t
        for t in models.Tiposdeacto.objects.filter(
            idtipoacto__in=all_act_codes, actouif__isnull=False
        ).exclude(actouif="")
    }
    if not tipos_uif:
        return {key: dict(_EMPTY_RESULT) for key in numbers}

    dashboard = UifDashboardService()
    (
        patrimonial_map,
        contratantes_map,
        clientes_map,
        contratantesxacto_map,
        detalle_medio_pago_map,
        fpago_codigo_map,
    ) = dashboard._bulk_fetch_related(numbers, list(tipos_uif.keys()))

    validator = RoEligibleRowValidator()
    out: Dict[str, Dict] = {}

    for key in numbers:
        kardex = kardex_by_key.get(key)
        if not kardex:
            out[key] = dict(_EMPTY_RESULT)
            continue

        act_codes = kardex_act_codes.get(key, [])
        if not any(cod in tipos_uif for cod in act_codes):
            out[key] = dict(_EMPTY_RESULT)
            continue

        try:
            uif_errors: List[dict] = []
            patrimonial_data: Dict[str, dict] = {}

            for cod_acto in act_codes:
                tipo_acto = tipos_uif.get(cod_acto)
                if not tipo_acto:
                    continue
                staged = _stage_kardex_row(kardex, cod_acto, tipo_acto, tipo="I")
                act_description = (
                    tipo_acto.desacto
                    if tipo_acto and tipo_acto.desacto
                    else f"Acto {cod_acto}"
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

            out[key] = {
                "has_uif_errors": len(uif_errors) > 0,
                "uif_errors": uif_errors,
                "uif_observations": [],
                "patrimonial_data": patrimonial_data,
            }
        except Exception as exc:
            logger.warning("UIF snapshot validation failed for %s: %s", key, exc)
            out[key] = {
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

    return out


def validate_kardex_number(kardex_number: str) -> Dict:
    """Shape consumed by SISGEN document search (`uif_validation` block)."""
    key = str(kardex_number or "").strip()
    if not key:
        return dict(_EMPTY_RESULT)
    return bulk_validate_kardex_numbers([key]).get(key, dict(_EMPTY_RESULT))
