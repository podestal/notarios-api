"""
Subsanar PDT — port of pdt/correct_error.php.

Applies only rows the UI posts (isCorrectable=1). Counts mysql_affected_rows
equivalents the same way PHP did (each successful UPDATE/INSERT increments).
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from django.db import connection

from .pdt_error_item import (
    CATEGORY_ACTOS,
    CATEGORY_BIENES,
    CATEGORY_MEDIO_PAGO,
    CATEGORY_OTORGANTES,
    TYPE_BIEN_DESCRIPCION,
    TYPE_BIEN_INSERT,
    TYPE_BIEN_RELINK,
    TYPE_MP_DOCUMENTOS,
    TYPE_MP_RELINK,
    TYPE_OTG_PORCENTAJE,
    TYPE_OTG_RENTA,
    TYPE_OTG_RUC,
)

logger = logging.getLogger(__name__)

DEFAULT_IDTIPBIEN = "10"
DEFAULT_OESPECIFIC = "VARIOS"
DEFAULT_TIPOB = "BIENES"
DEFAULT_DOCUMENTOS = "VOUCHER"
TIPDOC_SIN_RUC = 10


class PdtCorrectionService:
    """Apply Subsanar corrections (correct_error.php)."""

    def apply(self, error_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_ok = 0
        for row in error_list or []:
            try:
                total_ok += self._apply_one(row)
            except Exception as exc:
                logger.warning("PDT correction failed for %s: %s", row, exc, exc_info=True)

        return {
            "error": 0,
            "errorDescription": f"Se afectaron {total_ok} registros.",
        }

    @staticmethod
    def parse_payload(data: Any) -> Optional[List[Dict[str, Any]]]:
        """Accept `{ corrections: [...] }` or legacy `{ listError: "[{...}]" }`."""
        if not isinstance(data, dict):
            return None

        corrections = data.get("corrections")
        if isinstance(corrections, list) and corrections:
            return corrections

        list_error = data.get("listError")
        if isinstance(list_error, str) and list_error.strip():
            try:
                list_error = json.loads(list_error)
            except json.JSONDecodeError:
                return None
        if isinstance(list_error, list) and list_error:
            return list_error
        return None

    @staticmethod
    def _as_int(value: Any, default: int = 0) -> int:
        try:
            if value in (None, ""):
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _str(value: Any) -> str:
        if value in (None,):
            return ""
        return str(value).strip()

    def _apply_one(self, row: Dict[str, Any]) -> int:
        category = self._as_int(row.get("categoryCorrect"))
        type_corr = self._as_int(row.get("typeOfCorrection"))
        kardex = self._str(row.get("kardex"))
        tipo_acto = self._str(row.get("tipoActo") or row.get("typeAct"))
        item_mp = self._str(row.get("itemMp") or row.get("itemmp"))
        writing_date = self._str(row.get("writingDate"))
        id_contractor = self._str(row.get("idContractor") or row.get("idContratante"))

        if category == CATEGORY_ACTOS:
            return self._correct_actos(item_mp, writing_date)
        if category == CATEGORY_BIENES:
            return self._correct_bienes(type_corr, kardex, tipo_acto, item_mp)
        if category == CATEGORY_OTORGANTES:
            return self._correct_otorgantes(
                type_corr, kardex, tipo_acto, id_contractor
            )
        if category == CATEGORY_MEDIO_PAGO:
            return self._correct_medio(type_corr, kardex, tipo_acto, item_mp)
        return 0

    def _correct_actos(self, item_mp: str, writing_date: str) -> int:
        # UPDATE patrimonial SET nminuta = '$fechaEscritura' WHERE itemmp = '$itemMp'
        if not item_mp:
            return 0
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE patrimonial SET nminuta = %s WHERE itemmp = %s",
                [writing_date, item_mp],
            )
            return 1 if cursor.rowcount else 0

    def _correct_bienes(
        self, type_corr: int, kardex: str, tipo_acto: str, item_mp: str
    ) -> int:
        with connection.cursor() as cursor:
            if type_corr == TYPE_BIEN_RELINK:
                if not (kardex and tipo_acto and item_mp):
                    return 0
                cursor.execute(
                    """
                    UPDATE detallebienes
                    SET itemmp = %s
                    WHERE kardex = %s AND idtipacto = %s
                    """,
                    [item_mp, kardex, tipo_acto],
                )
                return 1 if cursor.rowcount else 0

            if type_corr == TYPE_BIEN_INSERT:
                if not (kardex and tipo_acto and item_mp):
                    return 0
                cursor.execute(
                    """
                    INSERT INTO detallebienes(
                        itemmp, kardex, idtipacto, tipob, idtipbien, oespecific,
                        coddis, fechaconst, smaquiequipo, tpsm, npsm, pregistral, idsedereg
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        '', '', '', '', '', '', ''
                    )
                    """,
                    [
                        item_mp,
                        kardex,
                        tipo_acto,
                        DEFAULT_TIPOB,
                        int(DEFAULT_IDTIPBIEN),
                        DEFAULT_OESPECIFIC,
                    ],
                )
                return 1 if cursor.rowcount else 0

            if type_corr == TYPE_BIEN_DESCRIPCION:
                if not item_mp:
                    return 0
                cursor.execute(
                    "UPDATE detallebienes SET oespecific = %s WHERE itemmp = %s",
                    [DEFAULT_OESPECIFIC, item_mp],
                )
                return 1 if cursor.rowcount else 0
        return 0

    def _correct_otorgantes(
        self,
        type_corr: int,
        kardex: str,
        tipo_acto: str,
        id_contractor: str,
    ) -> int:
        if type_corr == TYPE_OTG_RUC:
            if not id_contractor:
                return 0
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE cliente2
                    SET idtipdoc = %s, numdoc = %s
                    WHERE idcontratante = %s
                    """,
                    [TIPDOC_SIN_RUC, "", id_contractor],
                )
                return 1 if cursor.rowcount else 0

        if type_corr == TYPE_OTG_PORCENTAJE:
            return self._redistribute_porcentajes(kardex, tipo_acto)

        if type_corr == TYPE_OTG_RENTA:
            return self._insert_renta(kardex, id_contractor)
        return 0

    def _redistribute_porcentajes(self, kardex: str, tipo_acto: str) -> int:
        """Mirror correct_error.php parte 1 + parte 2 percentage split to 100."""
        if not (kardex and tipo_acto):
            return 0

        total_ok = 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT actosunat FROM tiposdeacto WHERE idtipoacto = %s LIMIT 1",
                [tipo_acto],
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return 0
            acto_sunat = str(row[0]).strip()

            for parte in (1, 2):
                contratantes = self._cxa_for_parte(
                    cursor, kardex, tipo_acto, acto_sunat, parte
                )
                count = len(contratantes)
                if count == 0:
                    continue

                target = Decimal("100")
                sum_parte = sum(
                    (Decimal(str(r[1] or 0)) for r in contratantes),
                    Decimal("0"),
                )
                if sum_parte == target:
                    continue

                each = (target / Decimal(count)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                # PHP: number_format($p/$count, 2, '.', '') then first gets remainder
                each_dec = Decimal(f"{each:.2f}")
                first = (target - (each_dec * Decimal(count - 1))).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

                for idx, (cxa_id, _old) in enumerate(contratantes):
                    pct = first if idx == 0 else each_dec
                    cursor.execute(
                        "UPDATE contratantesxacto SET porcentaje = %s WHERE id = %s",
                        [f"{pct:.2f}", int(cxa_id)],
                    )
                    if cursor.rowcount:
                        total_ok += 1
        return total_ok

    @staticmethod
    def _has_pdt_actos_tipo_otorgante(cursor) -> bool:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = 'pdt_actos_tipo_otorgante'
            LIMIT 1
            """
        )
        return cursor.fetchone() is not None

    def _cxa_for_parte(self, cursor, kardex, tipo_acto, acto_sunat, parte):
        """PHP uses pdt_actos_tipo_otorgante + actocondicion.totorgante; fallback to parte."""
        if self._has_pdt_actos_tipo_otorgante(cursor):
            cursor.execute(
                """
                SELECT tipoOtorgante
                FROM pdt_actos_tipo_otorgante
                WHERE actoSunat = %s AND parte = %s
                LIMIT 1
                """,
                [acto_sunat, parte],
            )
            tipo_row = cursor.fetchone()
            if tipo_row and tipo_row[0] not in (None, ""):
                cursor.execute(
                    """
                    SELECT contratantesxacto.id,
                           CAST(contratantesxacto.porcentaje AS DECIMAL(12,2)) AS porcentaje
                    FROM contratantesxacto
                    LEFT JOIN actocondicion
                      ON contratantesxacto.idcondicion = actocondicion.idcondicion
                    WHERE contratantesxacto.idtipoacto = %s
                      AND contratantesxacto.kardex = %s
                      AND actocondicion.totorgante = %s
                    """,
                    [tipo_acto, kardex, tipo_row[0]],
                )
                rows = cursor.fetchall()
                if rows:
                    return rows

        cursor.execute(
            """
            SELECT id, CAST(porcentaje AS DECIMAL(12,2)) AS porcentaje
            FROM contratantesxacto
            WHERE kardex = %s
              AND idtipoacto = %s
              AND TRIM(CAST(parte AS CHAR)) = %s
            """,
            [kardex, tipo_acto, str(parte)],
        )
        return cursor.fetchall()

    def _insert_renta(self, kardex: str, id_contractor: str) -> int:
        if not (kardex and id_contractor):
            return 0
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT LPAD((CAST(idrenta AS UNSIGNED) + 1), 6, '0') AS idRenta
                FROM renta
                ORDER BY idrenta DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            id_renta = row[0] if row and row[0] else "000001"
            cursor.execute(
                """
                INSERT INTO renta (idrenta, idcontratante, kardex, pregu1, pregu2, pregu3)
                VALUES (%s, %s, %s, '0', '0', '1')
                """,
                [id_renta, id_contractor, kardex],
            )
            return 1 if cursor.rowcount else 0

    def _correct_medio(
        self, type_corr: int, kardex: str, tipo_acto: str, item_mp: str
    ) -> int:
        with connection.cursor() as cursor:
            if type_corr == TYPE_MP_DOCUMENTOS:
                if not item_mp:
                    return 0
                cursor.execute(
                    "UPDATE detallemediopago SET documentos = %s WHERE itemmp = %s",
                    [DEFAULT_DOCUMENTOS, item_mp],
                )
                return 1 if cursor.rowcount else 0

            if type_corr == TYPE_MP_RELINK:
                if not (kardex and tipo_acto and item_mp):
                    return 0
                cursor.execute(
                    """
                    UPDATE detallemediopago
                    SET itemmp = %s
                    WHERE kardex = %s AND tipacto = %s
                    """,
                    [item_mp, kardex, tipo_acto],
                )
                return 1 if cursor.rowcount else 0
        return 0
