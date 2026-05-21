"""
UIF error dashboard — Phase 1: RoClass loadData staging + validation on `ro` rows.
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from notaria import models
from uif.services.date_utils import parse_date_range
from uif.services.load_data import RoLoadDataService
from uif.services.staging import RoStagedRecord

logger = logging.getLogger(__name__)


def patrimonial_key(kardex: str, act_code: str) -> Tuple[str, str]:
    return (kardex, str(act_code).zfill(3))


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
        patrimonial_map, contratantes_map, clientes_map, contratantesxacto_map = (
            self._bulk_fetch_related(kardex_numbers, list(all_act_codes))
        )

        errors: List[dict] = []
        valid_kardex_ro: List[dict] = []
        error_summary = {
            "missing_uif_code": 0,
            "missing_escritura_number": 0,
            "missing_conclusion_date": 0,
            "missing_patrimonial_data": 0,
            "invalid_act_codes": 0,
            "currency_without_amount": 0,
            "amount_mismatch": 0,
            "missing_participant_amount": 0,
        }

        seen_kardex_escritura: set = set()
        seen_kardex_conclusion: set = set()

        for staged in ro_records:
            tipo_acto = tipos_acto_map.get(staged.cod_acto)
            act_description = loader.act_description(staged.cod_acto)

            record_data = self._staged_to_record(staged, tipo_acto, act_description)

            patrimonial_errors = self._validate_patrimonial_data(
                staged.kardex,
                staged.cod_acto,
                act_description,
                patrimonial_map,
                contratantes_map,
                clientes_map,
                contratantesxacto_map,
            )

            if patrimonial_errors:
                errors.extend(patrimonial_errors)
                for error in patrimonial_errors:
                    et = error.get("error_type")
                    if et in error_summary:
                        error_summary[et] += 1
            else:
                patrimonial_data = self._get_patrimonial_summary(
                    staged.kardex, staged.cod_acto, patrimonial_map
                )
                record_data.update(patrimonial_data)
                valid_kardex_ro.append(record_data)

            escritura_key = (staged.id_kardex, staged.cod_acto)
            if (
                (not staged.numero_escritura or str(staged.numero_escritura).strip() == "")
                and escritura_key not in seen_kardex_escritura
            ):
                seen_kardex_escritura.add(escritura_key)
                errors.append(
                    {
                        "idkardex": staged.id_kardex,
                        "kardex": staged.kardex,
                        "act": act_description,
                        "status": "invalid",
                        "error_type": "missing_escritura_number",
                        "error_description": "Número de escritura faltante",
                    }
                )
                error_summary["missing_escritura_number"] += 1

            if not staged.fecha_conclusion and escritura_key not in seen_kardex_conclusion:
                seen_kardex_conclusion.add(escritura_key)
                errors.append(
                    {
                        "idkardex": staged.id_kardex,
                        "kardex": staged.kardex,
                        "act": act_description,
                        "status": "invalid",
                        "error_type": "missing_conclusion_date",
                        "error_description": "Fecha de conclusión faltante",
                    }
                )
                error_summary["missing_conclusion_date"] += 1

        kardex_no_envian = [self._ro_not_to_api(r, loader) for r in ro_not_records]

        return {
            "lista_errores": errors,
            "lista_kardex_ro": valid_kardex_ro,
            "lista_kardex_no_envian": kardex_no_envian,
            "summary": {
                "total_kardex": kardex_records.count(),
                "total_errors": len(errors),
                "total_valid_ro": len(valid_kardex_ro),
                "total_no_envian": len(kardex_no_envian),
                "total_ro_staged": len(ro_records),
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
                "phase": 1,
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

    def _bulk_fetch_related(self, kardex_numbers: List[str], act_codes: List[str]):
        patrimonial_map = {}
        if kardex_numbers and act_codes:
            for patrimonial in models.Patrimonial.objects.filter(
                kardex__in=kardex_numbers, idtipoacto__in=act_codes
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
            for cxa in models.Contratantesxacto.objects.filter(
                kardex__in=kardex_numbers,
                idtipoacto__in=act_codes,
                idcontratante__in=all_contratante_ids,
            ):
                key = f"{cxa.kardex}_{cxa.idtipoacto}_{cxa.idcontratante}"
                contratantesxacto_map[key] = cxa

        return patrimonial_map, contratantes_map, clientes_map, contratantesxacto_map

    def _validate_patrimonial_data(
        self,
        kardex: str,
        act_code: str,
        act_description: str,
        patrimonial_map,
        contratantes_map,
        clientes_map,
        contratantesxacto_map,
    ) -> List[dict]:
        patrimonial_errors = []
        try:
            patrimonial = patrimonial_map.get(patrimonial_key(kardex, act_code))
            if not patrimonial:
                return patrimonial_errors

            contratantes = contratantes_map.get(kardex, [])
            act_code_padded = str(act_code).zfill(3)

            if patrimonial.idmon and patrimonial.idmon != "":
                if not patrimonial.importetrans or patrimonial.importetrans == 0:
                    for contratante in contratantes:
                        cliente = clientes_map.get(contratante.idcontratante)
                        if cliente:
                            nombre = (
                                cliente.nombre
                                or cliente.razonsocial
                                or f"Contratante {contratante.idcontratante}"
                            )
                            patrimonial_errors.append(
                                {
                                    "idkardex": patrimonial.kardex,
                                    "kardex": kardex,
                                    "act": act_description,
                                    "status": "invalid",
                                    "error_type": "currency_without_amount",
                                    "error_description": (
                                        f"{nombre}, código de moneda no se debe informar sin montos"
                                    ),
                                }
                            )

            if patrimonial.importetrans and patrimonial.importetrans > 0:
                total_contratante_amounts = 0
                for contratante in contratantes:
                    cliente = clientes_map.get(contratante.idcontratante)
                    if not cliente:
                        continue
                    nombre = (
                        cliente.nombre
                        or cliente.razonsocial
                        or f"Contratante {contratante.idcontratante}"
                    )
                    contratante_acto_key = (
                        f"{kardex}_{act_code_padded}_{contratante.idcontratante}"
                    )
                    contratante_acto = contratantesxacto_map.get(
                        f"{kardex}_{act_code}_{contratante.idcontratante}"
                    ) or contratantesxacto_map.get(contratante_acto_key)

                    if contratante_acto and contratante_acto.monto:
                        try:
                            total_contratante_amounts += float(contratante_acto.monto)
                        except (ValueError, TypeError):
                            pass
                    else:
                        patrimonial_errors.append(
                            {
                                "idkardex": patrimonial.kardex,
                                "kardex": kardex,
                                "act": act_description,
                                "status": "invalid",
                                "error_type": "missing_participant_amount",
                                "error_description": f"{nombre} Monto por Participante",
                            }
                        )

                if total_contratante_amounts > 0:
                    patrimonial_total = float(patrimonial.importetrans)
                    if abs(total_contratante_amounts - patrimonial_total) > 0.01:
                        direction = (
                            "otorgantes"
                            if total_contratante_amounts > patrimonial_total
                            else "beneficierios"
                        )
                        patrimonial_errors.append(
                            {
                                "idkardex": patrimonial.kardex,
                                "kardex": kardex,
                                "act": act_description,
                                "status": "invalid",
                                "error_type": "amount_mismatch",
                                "error_description": (
                                    f"La suma de los montos de los contratantes {direction} "
                                    f"supera el monto total de la operacion: {patrimonial_total:.2f}"
                                ),
                            }
                        )
        except Exception as exc:
            logger.warning("Error validating patrimonial data for kardex %s: %s", kardex, exc)

        return patrimonial_errors

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
