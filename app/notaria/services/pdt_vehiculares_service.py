"""PDT Vehiculares validation (typeKardex=3) — flags match Cpu/PDTClass.php."""

from typing import Any, Dict, List

from django.db import connection

from .pdt_protocolar_mixin import (
    PdtProtocolarMixin,
    contractor_helpers,
    fetch_bulk_protocolar_context,
    parse_pdt_date_range,
)


class PdtVehicularesService(PdtProtocolarMixin):
    """Service for checking PDT errors in Vehicular acts."""

    def __init__(self, initial_date: str, final_date: str):
        self.initial_date = initial_date
        self.final_date = final_date
        self.total_kardex = 0
        self.errors: List[Dict[str, Any]] = []

    def load_data(self) -> None:
        try:
            start_date, end_date = parse_pdt_date_range(
                self.initial_date, self.final_date
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        k.kardex,
                        k.idkardex,
                        k.numescritura,
                        k.fechaescritura,
                        p.itemmp,
                        p.nminuta,
                        p.exhibiomp,
                        p.idtipoacto,
                        t.desacto,
                        t.actosunat,
                        IF(
                            k.fechaescritura <= STR_TO_DATE(k.fechaconclusion,'%%d/%%m/%%Y'),
                            0, 1
                        ) AS fecha_validation
                    FROM kardex k
                    INNER JOIN patrimonial p ON k.kardex = p.kardex
                    LEFT JOIN tiposdeacto t ON t.idtipoacto = p.idtipoacto
                    WHERE k.idtipkar = 3
                      AND STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y')
                          BETWEEN %s AND %s
                    ORDER BY k.kardex ASC
                    """,
                    [start_date, end_date],
                )
                rows = cursor.fetchall()
                self.total_kardex = len(rows)
                if not rows:
                    return

                kardex_list = [row[0] for row in rows]
                ctx = fetch_bulk_protocolar_context(cursor, kardex_list)

            for row in rows:
                (
                    kardex,
                    id_kardex,
                    num_escritura,
                    fecha_escritura,
                    item_mp,
                    nminuta,
                    exhibio_mp,
                    idtipoacto,
                    acto,
                    acto_sunat,
                    fecha_validation,
                ) = row

                helpers = contractor_helpers(ctx["contratantes"].get(kardex, []))
                idtipoacto_s = str(idtipoacto or "").strip()
                self._validate_common_row(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    num_escritura=num_escritura,
                    fecha_escritura=fecha_escritura,
                    nminuta=nminuta,
                    acto=acto or "",
                    acto_sunat=str(acto_sunat or ""),
                    idtipoacto=idtipoacto,
                    item_mp=item_mp,
                    fecha_validation=int(fecha_validation or 0),
                    exhibio_mp=exhibio_mp,
                    bienes_by_item=ctx["bienes_by_item"],
                    bienes_by_acto=ctx["bienes_by_acto"],
                    bienes_need_desc=ctx["bienes_need_desc"],
                    has_medio_by_item=ctx["has_medio_by_item"],
                    has_medio_by_acto=ctx["has_medio_by_acto"],
                    empty_doc_medios=ctx["empty_doc_medios"],
                    has_formulario=ctx["has_formulario"],
                    renta_keys=ctx["renta_keys"],
                    porcentaje_by_parte={kardex: helpers["porcentaje_by_parte"]},
                    ruc_bad_contractors=helpers["ruc_bad"],
                    missing_roles={
                        "renta_candidates": helpers["renta_candidates"],
                        "has_fecha_adquisicion": (
                            kardex,
                            idtipoacto_s,
                        )
                        in ctx["bienes_has_fecha_adq"],
                    },
                )
        except Exception as e:
            raise Exception(f"Error loading vehicular data: {str(e)}") from e
