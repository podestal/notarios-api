"""UIF issues for compliance — same engine as the UIF report/dashboard."""

from __future__ import annotations

import calendar
from datetime import date
from typing import Dict, List

from notaria import models
from compliance.services.kardex_meta import parse_kardex_date
from compliance.services.payload import build_uif_block
from uif.services.dashboard_service import UifDashboardService
from uif.services.generate_data import RoGenerateDataService
from uif.services.load_data import _parse_act_codes, _stage_kardex_row
from uif.services.ro_validator import RoEligibleRowValidator

_EMPTY = {
    "has_uif_errors": False,
    "uif_errors": [],
    "uif_observations": [],
    "patrimonial_data": {},
}


def _month_bounds(d: date) -> tuple[date, date]:
    last = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, 1), date(d.year, d.month, last)


def validate_kardex_like_uif_report(kardex_number: str) -> Dict:
    """
    Single-kardex UIF validation matching ``UifDashboardService``:
    threshold gate + ``RoEligibleRowValidator`` with the escritura month as range.
    """
    key = str(kardex_number or "").strip()
    if not key:
        return dict(_EMPTY)

    kardex = models.Kardex.objects.filter(kardex=key).first()
    if not kardex:
        return dict(_EMPTY)

    act_codes = _parse_act_codes(kardex.codactos or "")
    if not act_codes:
        return dict(_EMPTY)

    tipos_uif = {
        t.idtipoacto: t
        for t in models.Tiposdeacto.objects.filter(
            idtipoacto__in=act_codes, actouif__isnull=False
        ).exclude(actouif="")
    }
    if not tipos_uif:
        return dict(_EMPTY)

    escritura = parse_kardex_date(kardex.fechaescritura)
    if escritura:
        range_start, range_end = _month_bounds(escritura)
    else:
        range_start = range_end = None

    staged_rows = []
    for cod_acto in act_codes:
        tipo_acto = tipos_uif.get(cod_acto)
        if not tipo_acto:
            continue
        staged_rows.append(_stage_kardex_row(kardex, cod_acto, tipo_acto, tipo="I"))

    if not staged_rows:
        return dict(_EMPTY)

    dashboard = UifDashboardService()
    (
        patrimonial_map,
        contratantes_map,
        clientes_map,
        contratantesxacto_map,
        detalle_medio_pago_map,
        fpago_codigo_map,
    ) = dashboard._bulk_fetch_related([key], list(tipos_uif.keys()))

    eligible, _below = RoGenerateDataService().partition_by_threshold(
        staged_rows, patrimonial_map
    )
    if not eligible:
        return dict(_EMPTY)

    validator = RoEligibleRowValidator()
    uif_errors: List[dict] = []
    patrimonial_data: Dict[str, dict] = {}

    for staged in eligible:
        tipo_acto = tipos_uif.get(staged.cod_acto)
        act_description = (
            tipo_acto.desacto
            if tipo_acto and tipo_acto.desacto
            else f"Acto {staged.cod_acto}"
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
            range_start=range_start,
            range_end=range_end,
        )
        if row_errors:
            uif_errors.extend(row_errors)
        else:
            summary = dashboard._get_patrimonial_summary(
                key, staged.cod_acto, patrimonial_map
            )
            patrimonial_data[staged.cod_acto] = summary

    return {
        "has_uif_errors": len(uif_errors) > 0,
        "uif_errors": uif_errors,
        "uif_observations": [],
        "patrimonial_data": patrimonial_data,
    }


def collect_uif_issues(kardex: str) -> dict:
    return build_uif_block(validate_kardex_like_uif_report(kardex))
