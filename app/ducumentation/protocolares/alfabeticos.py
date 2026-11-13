"""
Índices alfabéticos (protocolares) — mirrors legacy PHP:

  consultas/alfabeticos/{escrituras,garantias,asuntos,vehiculares,testamentos}.php

Criteria (same for all tipkar):
  - kardex.idtipkar = tipkar
  - fechaescritura between desde/hasta
  - INNER JOIN contratantes WHERE indice='1'
  - INNER JOIN cliente2
  - ORDER BY cliente ASC

Excel/Word downloads reuse each cronológico ReportService payload, then sort by
otorgante/testador (same as excel/alfabetico/reporteAlfa*.php).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.db import connection

from ducumentation.protocolares.EscrituraPublicaDocumentService import (
    EscriturasPublicasReportService,
)
from ducumentation.protocolares.GarantiasService import GarantiasReportService
from ducumentation.protocolares.NoContenciososService import NoContenciososReportService
from ducumentation.protocolares.TestamentosService import TestamentosReportService
from ducumentation.protocolares.TransferenciasVehicularesService import (
    TransferenciasVehicularesReportService,
)

# tipkar → (service class, human label for errors)
ALFABETICO_SERVICES = {
    "1": (EscriturasPublicasReportService, "escrituras"),
    "2": (NoContenciososReportService, "no-contenciosos"),
    "3": (TransferenciasVehicularesReportService, "transferencias"),
    "4": (GarantiasReportService, "garantias"),
    "5": (TestamentosReportService, "testamentos"),
}

TIPKAR_BY_SLUG = {
    "escrituras": "1",
    "no-contenciosos": "2",
    "asuntos": "2",
    "transferencias": "3",
    "vehiculares": "3",
    "garantias": "4",
    "testamentos": "5",
}


def parse_report_date(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Fecha requerida")
    if "-" in raw and len(raw.split("-")[0]) == 4:
        return datetime.strptime(raw, "%Y-%m-%d")
    if "/" in raw:
        return datetime.strptime(raw, "%d/%m/%Y")
    raise ValueError(f"Formato de fecha inválido: {raw}")


def sort_report_rows_alfabetico(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort cronológico-shaped rows like PHP array_sort(..., 'otorgante')."""

    def sort_key(row: Dict[str, Any]) -> Tuple[str, str]:
        name = (
            row.get("otorgante")
            or row.get("testador")
            or row.get("cliente")
            or ""
        )
        return (str(name).casefold(), str(row.get("numero_escritura") or ""))

    return sorted(rows or [], key=sort_key)


def _cliente_sql_expr() -> str:
    return """
        UPPER((CASE
            WHEN (cliente2.tipper = 'N') THEN TRIM(CONCAT(
                COALESCE(cliente2.apepat, ''), ' ',
                COALESCE(cliente2.apemat, ''), ' ',
                COALESCE(cliente2.prinom, ''), ' ',
                COALESCE(cliente2.segnom, '')
            ))
            ELSE COALESCE(cliente2.razonsocial, '')
        END))
    """


class AlfabeticosReportService:
    """List + download helpers for índices alfabéticos protocolares."""

    PAGE_SIZE = 10

    def list_rows(
        self,
        idtipkar: str,
        desde: str,
        hasta: str,
        page: int = 1,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        tipkar = str(idtipkar).strip()
        if tipkar not in ALFABETICO_SERVICES:
            raise ValueError(f"idtipkar no soportado para alfabeticos: {tipkar}")

        desde_dt = parse_report_date(desde)
        hasta_dt = parse_report_date(hasta)
        page = max(1, int(page or 1))
        size = max(1, int(page_size or self.PAGE_SIZE))
        offset = (page - 1) * size
        cliente_expr = _cliente_sql_expr()

        count_sql = f"""
            SELECT COUNT(*)
            FROM kardex
            INNER JOIN contratantes
                ON contratantes.kardex = kardex.kardex
                AND contratantes.indice = '1'
            INNER JOIN cliente2
                ON cliente2.idcontratante = contratantes.idcontratante
            WHERE kardex.idtipkar = %s
              AND STR_TO_DATE(kardex.fechaescritura, '%%Y-%%m-%%d')
                    >= STR_TO_DATE(%s, '%%Y-%%m-%%d')
              AND STR_TO_DATE(kardex.fechaescritura, '%%Y-%%m-%%d')
                    <= STR_TO_DATE(%s, '%%Y-%%m-%%d')
        """

        data_sql = f"""
            SELECT
                {cliente_expr} AS cliente,
                kardex.fechaescritura,
                kardex.kardex,
                kardex.contrato,
                kardex.numescritura,
                kardex.numminuta,
                kardex.folioini
            FROM kardex
            INNER JOIN contratantes
                ON contratantes.kardex = kardex.kardex
                AND contratantes.indice = '1'
            INNER JOIN cliente2
                ON cliente2.idcontratante = contratantes.idcontratante
            WHERE kardex.idtipkar = %s
              AND STR_TO_DATE(kardex.fechaescritura, '%%Y-%%m-%%d')
                    >= STR_TO_DATE(%s, '%%Y-%%m-%%d')
              AND STR_TO_DATE(kardex.fechaescritura, '%%Y-%%m-%%d')
                    <= STR_TO_DATE(%s, '%%Y-%%m-%%d')
            ORDER BY cliente ASC
            LIMIT %s OFFSET %s
        """

        params_range = [
            tipkar,
            desde_dt.strftime("%Y-%m-%d"),
            hasta_dt.strftime("%Y-%m-%d"),
        ]

        with connection.cursor() as cursor:
            cursor.execute(count_sql, params_range)
            total = int(cursor.fetchone()[0] or 0)
            cursor.execute(data_sql, params_range + [size, offset])
            columns = [col[0] for col in cursor.description]
            raw_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        results = []
        for row in raw_rows:
            fecha = row.get("fechaescritura") or ""
            if hasattr(fecha, "strftime"):
                fecha_str = fecha.strftime("%d/%m/%Y")
            else:
                fecha_raw = str(fecha)
                if len(fecha_raw) >= 10 and fecha_raw[4] == "-":
                    fecha_str = f"{fecha_raw[8:10]}/{fecha_raw[5:7]}/{fecha_raw[0:4]}"
                else:
                    fecha_str = fecha_raw
            results.append(
                {
                    "cliente": (row.get("cliente") or "").strip(),
                    "fechaescritura": fecha_str,
                    "kardex": row.get("kardex") or "",
                    "contrato": row.get("contrato") or "",
                    "numescritura": row.get("numescritura") or "",
                    "numminuta": row.get("numminuta") or "",
                    "folioini": row.get("folioini") or "",
                }
            )

        return {
            "count": total,
            "page": page,
            "page_size": size,
            "num_pages": (total + size - 1) // size if size else 0,
            "idtipkar": tipkar,
            "results": results,
        }

    def generate_report(
        self,
        idtipkar: str,
        desde: str,
        hasta: str,
        tipo_documento: Optional[str] = None,
    ):
        tipkar = str(idtipkar).strip()
        if tipkar not in ALFABETICO_SERVICES:
            raise ValueError(f"idtipkar no soportado para alfabeticos: {tipkar}")

        service_cls, _ = ALFABETICO_SERVICES[tipkar]
        service = service_cls()
        tipo = (tipo_documento or "").strip().upper()
        if tipo == "EXCEL":
            return service.generate_excel_report(desde=desde, hasta=hasta, alfabetico=True)
        return service.generate_word_report(desde=desde, hasta=hasta, alfabetico=True)
