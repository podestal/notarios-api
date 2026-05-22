"""
UIF error dashboard — Phase 3: ro_validation_by_act + nested RO error metadata.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from notaria import models
from uif.services.date_utils import parse_date_range
from uif.services.generate_data import RoGenerateDataService
from uif.services.keys import patrimonial_key
from uif.services.load_data import RoLoadDataService
from uif.models import FpagoUif
from uif.services.ro_validator import RoEligibleRowValidator
from uif.services.staging import RoStagedRecord

logger = logging.getLogger(__name__)


class UifDashboardService:
    """Builds the three-tab UIF dashboard payload (errors, RO, no envían)."""

    def build_response(self, request, paginate_fn, get_paginated_response_fn) -> Response:
        initial_date = request.query_params.get("initialDate")
        final_date = request.query_params.get("finalDate")
        include_valid = request.query_params.get("includeValid", "false").lower() == "true"
        filter_type = (request.query_params.get("type") or "errors").strip().lower()
        tab_keys = {
            "errors": "lista_errores",
            "ro": "lista_kardex_ro",
            "no_envian": "lista_kardex_no_envian",
        }
        if filter_type not in tab_keys:
            filter_type = "errors"

        if not initial_date or not final_date:
            return Response(
                {"error": "Both initialDate and finalDate are required (DD/MM/YYYY format)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parsed = parse_date_range(initial_date, final_date)
        if isinstance(parsed, Response):
            return parsed
        start_date, end_date = parsed

        try:
            payload = self.run(start_date, end_date, initial_date, final_date, include_valid)
        except Exception as exc:
            logger.error("Error in UIF error dashboard: %s", exc, exc_info=True)
            return Response(
                {
                    "error": "Internal server error while processing UIF validation",
                    "detail": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        data_key = tab_keys[filter_type]
        paginated_data = paginate_fn(payload[data_key])

        # Only the active tab carries rows; other lists are empty (summary keeps totals).
        response_data = {
            "lista_errores": paginated_data if filter_type == "errors" else [],
            "lista_errores_agrupados": payload.get("lista_errores_agrupados", {}),
            "lista_kardex_ro": paginated_data if filter_type == "ro" else [],
            "lista_kardex_no_envian": paginated_data if filter_type == "no_envian" else [],
            "summary": payload["summary"],
            "metadata": {
                **payload["metadata"],
                "current_filter": filter_type,
                "paginated_category": data_key,
            },
        }

        if include_valid:
            response_data["valid_records"] = payload["lista_kardex_ro"]
            response_data["summary"]["total_valid"] = len(payload["lista_kardex_ro"])

        return get_paginated_response_fn(response_data)

    def run(
        self,
        start_date: date,
        end_date: date,
        initial_date: str,
        final_date: str,
        include_valid: bool,
    ) -> Dict[str, Any]:
        loader = RoLoadDataService()
        ro_records, ro_not_records = loader.load(start_date, end_date)

        kardex_records = (
            models.Kardex.objects.filter(fechaescritura__range=[start_date, end_date])
            .exclude(idtipkar__in=[2, 5])
            .order_by("-idkardex")
        )

        all_act_codes = set()
        for staged in ro_records + ro_not_records:
            all_act_codes.add(staged.cod_acto)

        tipos_acto_map = {
            t.idtipoacto: t
            for t in models.Tiposdeacto.objects.filter(
                idtipoacto__in=list(all_act_codes), actouif__isnull=False
            ).exclude(actouif="")
        }

        kardex_numbers = list({s.kardex for s in ro_records})
        (
            patrimonial_map,
            contratantes_map,
            clientes_map,
            contratantesxacto_map,
            detalle_medio_pago_map,
            fpago_codigo_map,
        ) = self._bulk_fetch_related(kardex_numbers, list(all_act_codes))

        generate_service = RoGenerateDataService()
        eligible_ro, below_threshold_ro = generate_service.partition_by_threshold(
            ro_records, patrimonial_map
        )

        row_validator = RoEligibleRowValidator()
        errors: List[dict] = []
        valid_kardex_ro: List[dict] = []
        report_kardex_ro: List[dict] = []
        error_summary: Dict[str, int] = {"below_threshold": 0}

        for staged in eligible_ro:
            tipo_acto = tipos_acto_map.get(staged.cod_acto)
            act_description = loader.act_description(staged.cod_acto)
            record_data = self._staged_to_record(staged, tipo_acto, act_description)
            record_data.update(
                self._get_patrimonial_summary(staged.kardex, staged.cod_acto, patrimonial_map)
            )

            row_errors = row_validator.validate_row(
                staged,
                act_description,
                patrimonial_map,
                contratantes_map,
                clientes_map,
                contratantesxacto_map,
                detalle_medio_pago_map,
                fpago_codigo_map,
                range_start=start_date,
                range_end=end_date,
            )

            if row_errors:
                errors.extend(row_errors)
                record_data["has_validation_errors"] = True
                record_data["validation_error_count"] = len(row_errors)
                record_data["status"] = "with_errors"
            else:
                record_data["has_validation_errors"] = False
                record_data["validation_error_count"] = 0
                valid_kardex_ro.append(record_data)

            # PHP generateFileRo uses _arrObjRo (all generateData rows), not only zero-error acts.
            report_kardex_ro.append(record_data)

        breakdown, errors_grouped = row_validator.summarize_errors(errors)
        for key, count in breakdown.items():
            error_summary[key] = error_summary.get(key, 0) + count

        kardex_no_envian = [self._ro_not_to_api(r, loader) for r in ro_not_records]
        kardex_no_envian.extend(
            self._below_threshold_to_api(r, loader, patrimonial_map) for r in below_threshold_ro
        )
        error_summary["below_threshold"] = len(below_threshold_ro)

        return {
            "lista_errores": errors,
            "lista_errores_agrupados": errors_grouped,
            "lista_kardex_ro": valid_kardex_ro,
            "lista_kardex_report": report_kardex_ro,
            "lista_kardex_no_envian": kardex_no_envian,
            "summary": {
                "total_kardex": kardex_records.count(),
                "total_errors": len(errors),
                "total_valid_ro": len(valid_kardex_ro),
                "total_report_ro": len(report_kardex_ro),
                "total_report_with_errors": sum(
                    1 for r in report_kardex_ro if r.get("has_validation_errors")
                ),
                "total_no_envian": len(kardex_no_envian),
                "total_ro_staged": len(ro_records),
                "total_ro_eligible": len(eligible_ro),
                "total_ro_below_threshold": len(below_threshold_ro),
                "total_ro_not_staged": len(ro_not_records),
                "error_breakdown": error_summary,
                "date_range": {
                    "start": initial_date,
                    "end": final_date,
                    "start_iso": start_date.isoformat(),
                    "end_iso": end_date.isoformat(),
                    "start_formatted": start_date.strftime("%d/%m/%Y"),
                    "end_formatted": end_date.strftime("%d/%m/%Y"),
                },
            },
            "metadata": {
                "processed_at": timezone.now().isoformat(),
                "include_valid_records": include_valid,
                "engine": "uif",
                "phase": 6,
                "report_policy_default": "all",
            },
        }

    @staticmethod
    def _staged_to_record(
        staged: RoStagedRecord,
        tipo_acto: Optional[models.Tiposdeacto],
        act_description: str,
    ) -> dict:
        return {
            "idkardex": staged.id_kardex,
            "kardex": staged.kardex,
            "idtipkar": staged.id_tipo_kardex,
            "tipo_instrumento": staged.tipo_instrumento,
            "codacto": staged.cod_acto,
            "numescritura": staged.numero_escritura,
            "fechaescritura": staged.fecha_escritura,
            "fechaconclusion": staged.fecha_conclusion,
            "tipo": staged.tipo,
            "act": act_description,
            "uif_code": staged.uif_code,
            "umbral": tipo_acto.umbral if tipo_acto else None,
            "status": "valid",
            "validation_errors": [],
        }

    @staticmethod
    def _ro_not_to_api(staged: RoStagedRecord, loader: RoLoadDataService) -> dict:
        return {
            "idkardex": staged.id_kardex,
            "kardex": staged.kardex,
            "idtipkar": staged.id_tipo_kardex,
            "tipo_instrumento": staged.tipo_instrumento,
            "codacto": staged.cod_acto,
            "act": loader.act_description(staged.cod_acto),
            "numescritura": staged.numero_escritura,
            "fechaescritura": staged.fecha_escritura,
            "fechaconclusion": staged.fecha_conclusion,
            "tipo": staged.tipo,
            "status": "no_envian",
            "reason": "Acto sin código UIF (ro_not)",
        }

    def _below_threshold_to_api(
        self, staged: RoStagedRecord, loader: RoLoadDataService, patrimonial_map: Dict
    ) -> dict:
        record = self._ro_not_to_api(staged, loader)
        record["reason"] = "Monto por debajo del umbral UIF (ro=0)"
        record["uif_code"] = staged.uif_code
        record.update(self._get_patrimonial_summary(staged.kardex, staged.cod_acto, patrimonial_map))
        return record

    def _bulk_fetch_related(self, kardex_numbers: List[str], act_codes: List[str]):
        patrimonial_map = {}
        if kardex_numbers and act_codes:
            act_filter = list({*act_codes, *[str(a).zfill(3) for a in act_codes]})
            for patrimonial in models.Patrimonial.objects.filter(
                kardex__in=kardex_numbers, idtipoacto__in=act_filter
            ):
                key = patrimonial_key(patrimonial.kardex, str(patrimonial.idtipoacto))
                patrimonial_map[key] = patrimonial

        contratantes_map = {}
        if kardex_numbers:
            for contratante in models.Contratantes.objects.filter(kardex__in=kardex_numbers):
                contratantes_map.setdefault(contratante.kardex, []).append(contratante)

        all_contratante_ids = [
            c.idcontratante for clist in contratantes_map.values() for c in clist
        ]

        clientes_map = {}
        if all_contratante_ids:
            for cliente in models.Cliente2.objects.filter(idcontratante__in=all_contratante_ids):
                clientes_map[cliente.idcontratante] = cliente

        contratantesxacto_map = {}
        if all_contratante_ids and kardex_numbers and act_codes:
            act_filter = list({*act_codes, *[str(a).zfill(3) for a in act_codes]})
            for cxa in models.Contratantesxacto.objects.filter(
                kardex__in=kardex_numbers,
                idtipoacto__in=act_filter,
                idcontratante__in=all_contratante_ids,
            ):
                key = f"{cxa.kardex}_{cxa.idtipoacto}_{cxa.idcontratante}"
                contratantesxacto_map[key] = cxa
                key_z = f"{cxa.kardex}_{str(cxa.idtipoacto).zfill(3)}_{cxa.idcontratante}"
                contratantesxacto_map[key_z] = cxa

        detalle_medio_pago_map = {}
        if kardex_numbers:
            for detalle in models.Detallemediopago.objects.filter(kardex__in=kardex_numbers):
                detalle_medio_pago_map.setdefault(detalle.kardex, []).append(detalle)

        fpago_codigo_map = {
            str(row.id_fpago): (row.codigo or "") for row in FpagoUif.objects.all()
        }

        return (
            patrimonial_map,
            contratantes_map,
            clientes_map,
            contratantesxacto_map,
            detalle_medio_pago_map,
            fpago_codigo_map,
        )

    def _get_patrimonial_summary(self, kardex_number: str, act_code: str, patrimonial_map) -> dict:
        defaults = {
            "tipo_moneda": "SOLES",
            "tipo_cambio": 0.0,
            "patrimonial": 0.0,
            "en_dolares": 0.0,
            "currency_symbol": "S./ ",
        }
        try:
            patrimonial = patrimonial_map.get(patrimonial_key(kardex_number, act_code))
            if not patrimonial:
                return defaults

            if patrimonial.idmon == 2:
                currency_symbol = "$ "
                currency_description = "DOLARES"
            else:
                currency_symbol = "S./ "
                currency_description = "SOLES"

            tipo_cambio = float(patrimonial.tipocambio) if patrimonial.tipocambio else 1.0
            importe_trans = float(patrimonial.importetrans) if patrimonial.importetrans else 0.0

            if patrimonial.idmon == 1:
                en_dolares = importe_trans / tipo_cambio if tipo_cambio > 0 else 0.0
            else:
                en_dolares = importe_trans

            return {
                "tipo_moneda": currency_description,
                "tipo_cambio": tipo_cambio,
                "patrimonial": importe_trans,
                "en_dolares": round(en_dolares, 2),
                "currency_symbol": currency_symbol,
            }
        except Exception as exc:
            logger.warning(
                "Error getting patrimonial summary for kardex %s: %s", kardex_number, exc
            )
            return defaults
