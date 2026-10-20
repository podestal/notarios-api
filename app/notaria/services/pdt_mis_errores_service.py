"""
Mis errores PDT — ports getErrors.php / ranking of responsables.

Four checks (same SQL as legacy PHP), filtered by year of fechaescritura
and kardex.responsable_new:

- renta: acto 030, parte=1, renta questions empty
- bien: actos 030/084/033/036/037/047/024 without a valid bien
- ofondo: acto 094, parte 1 or 2, empty origin of funds
- conclusion: empty fechaconclusion

PHP ranking JS expects ``[{nombre, user, total}]``. The ranking PHP that was
pasted was a copy of getErrors.php; this service aggregates the same four
checks by responsable_new.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from django.db import connection

from notaria.models import Usuarios

RENTA_SQL = """
    SELECT
        k.idkardex AS id_kardex,
        k.kardex AS kardex_esc,
        k.contrato AS acto,
        k.responsable_new AS responsable,
        k.fechaescritura,
        IF(c2.tipper='J', c2.razonsocial, c2.nombre) AS contratante
    FROM kardex AS k
    INNER JOIN contratantes AS con ON con.kardex = k.kardex
    INNER JOIN cliente2 AS c2 ON c2.idcontratante = con.idcontratante
    INNER JOIN contratantesxacto AS cxa ON cxa.idcontratante = con.idcontratante
    LEFT JOIN renta AS re ON re.idcontratante = con.idcontratante
    WHERE cxa.parte = 1
      AND LOWER(TRIM(k.responsable_new)) = LOWER(%s)
      AND k.codactos = '030'
      AND (re.pregu1 IS NULL OR re.pregu2 IS NULL OR re.pregu3 IS NULL)
      AND YEAR(k.fechaescritura) = %s
    ORDER BY k.idkardex ASC
"""

BIEN_SQL = """
    SELECT
        k.idkardex AS id_kardex,
        k.kardex AS kardex_esc,
        k.contrato AS acto,
        k.responsable_new AS responsable,
        k.fechaescritura
    FROM kardex AS k
    LEFT JOIN detallebienes AS db ON db.kardex = k.kardex
    WHERE LOWER(TRIM(k.responsable_new)) = LOWER(%s)
      AND k.codactos IN ('030', '084', '033', '036', '037', '047', '024')
      AND (db.detbien IS NULL OR db.idtipbien = 0 OR db.tipob = '')
      AND YEAR(k.fechaescritura) = %s
    ORDER BY k.idkardex ASC
"""

OFONDO_SQL = """
    SELECT
        k.idkardex AS id_kardex,
        k.kardex AS kardex_esc,
        k.contrato AS acto,
        k.responsable_new AS responsable,
        k.fechaescritura,
        c2.nombre AS contratante
    FROM kardex AS k
    LEFT JOIN contratantesxacto AS cxa ON cxa.kardex = k.kardex
    LEFT JOIN cliente2 AS c2 ON c2.idcontratante = cxa.idcontratante
    WHERE LOWER(TRIM(k.responsable_new)) = LOWER(%s)
      AND k.codactos = '094'
      AND (cxa.ofondo = '' OR cxa.ofondo IS NULL)
      AND (cxa.parte = '1' OR cxa.parte = '2')
      AND YEAR(k.fechaescritura) = %s
    ORDER BY k.idkardex ASC
"""

CONCLUSION_SQL = """
    SELECT
        k.idkardex AS id_kardex,
        k.kardex AS kardex_esc,
        k.contrato AS acto,
        k.responsable_new AS responsable,
        k.fechaescritura
    FROM kardex AS k
    WHERE LOWER(TRIM(k.responsable_new)) = LOWER(%s)
      AND (k.fechaconclusion = '' OR k.fechaconclusion IS NULL)
      AND YEAR(k.fechaescritura) = %s
    ORDER BY k.idkardex ASC
"""

# Same four PHP checks, scoped to one kardex (Panel General / compliance).
RENTA_BY_KARDEX_SQL = """
    SELECT
        k.idkardex AS id_kardex,
        k.kardex AS kardex_esc,
        k.contrato AS acto,
        k.responsable_new AS responsable,
        k.fechaescritura,
        IF(c2.tipper='J', c2.razonsocial, c2.nombre) AS contratante
    FROM kardex AS k
    INNER JOIN contratantes AS con ON con.kardex = k.kardex
    INNER JOIN cliente2 AS c2 ON c2.idcontratante = con.idcontratante
    INNER JOIN contratantesxacto AS cxa ON cxa.idcontratante = con.idcontratante
    LEFT JOIN renta AS re ON re.idcontratante = con.idcontratante
    WHERE cxa.parte = 1
      AND k.kardex = %s
      AND k.codactos = '030'
      AND (re.pregu1 IS NULL OR re.pregu2 IS NULL OR re.pregu3 IS NULL)
    ORDER BY k.idkardex ASC
"""

BIEN_BY_KARDEX_SQL = """
    SELECT
        k.idkardex AS id_kardex,
        k.kardex AS kardex_esc,
        k.contrato AS acto,
        k.responsable_new AS responsable,
        k.fechaescritura
    FROM kardex AS k
    LEFT JOIN detallebienes AS db ON db.kardex = k.kardex
    WHERE k.kardex = %s
      AND k.codactos IN ('030', '084', '033', '036', '037', '047', '024')
      AND (db.detbien IS NULL OR db.idtipbien = 0 OR db.tipob = '')
    ORDER BY k.idkardex ASC
"""

OFONDO_BY_KARDEX_SQL = """
    SELECT
        k.idkardex AS id_kardex,
        k.kardex AS kardex_esc,
        k.contrato AS acto,
        k.responsable_new AS responsable,
        k.fechaescritura,
        c2.nombre AS contratante
    FROM kardex AS k
    LEFT JOIN contratantesxacto AS cxa ON cxa.kardex = k.kardex
    LEFT JOIN cliente2 AS c2 ON c2.idcontratante = cxa.idcontratante
    WHERE k.kardex = %s
      AND k.codactos = '094'
      AND (cxa.ofondo = '' OR cxa.ofondo IS NULL)
      AND (cxa.parte = '1' OR cxa.parte = '2')
    ORDER BY k.idkardex ASC
"""

CONCLUSION_BY_KARDEX_SQL = """
    SELECT
        k.idkardex AS id_kardex,
        k.kardex AS kardex_esc,
        k.contrato AS acto,
        k.responsable_new AS responsable,
        k.fechaescritura
    FROM kardex AS k
    WHERE k.kardex = %s
      AND (k.fechaconclusion = '' OR k.fechaconclusion IS NULL)
    ORDER BY k.idkardex ASC
"""

COUNT_BY_KARDEX_SQL = """
    SELECT kardex_esc AS kardex, COUNT(*) AS total FROM (
        SELECT k.kardex AS kardex_esc
        FROM kardex AS k
        INNER JOIN contratantes AS con ON con.kardex = k.kardex
        INNER JOIN cliente2 AS c2 ON c2.idcontratante = con.idcontratante
        INNER JOIN contratantesxacto AS cxa ON cxa.idcontratante = con.idcontratante
        LEFT JOIN renta AS re ON re.idcontratante = con.idcontratante
        WHERE cxa.parte = 1
          AND k.codactos = '030'
          AND (re.pregu1 IS NULL OR re.pregu2 IS NULL OR re.pregu3 IS NULL)
          AND k.kardex IN ({placeholders})

        UNION ALL

        SELECT k.kardex AS kardex_esc
        FROM kardex AS k
        LEFT JOIN detallebienes AS db ON db.kardex = k.kardex
        WHERE k.codactos IN ('030', '084', '033', '036', '037', '047', '024')
          AND (db.detbien IS NULL OR db.idtipbien = 0 OR db.tipob = '')
          AND k.kardex IN ({placeholders})

        UNION ALL

        SELECT k.kardex AS kardex_esc
        FROM kardex AS k
        LEFT JOIN contratantesxacto AS cxa ON cxa.kardex = k.kardex
        WHERE k.codactos = '094'
          AND (cxa.ofondo = '' OR cxa.ofondo IS NULL)
          AND (cxa.parte = '1' OR cxa.parte = '2')
          AND k.kardex IN ({placeholders})

        UNION ALL

        SELECT k.kardex AS kardex_esc
        FROM kardex AS k
        WHERE (k.fechaconclusion = '' OR k.fechaconclusion IS NULL)
          AND k.kardex IN ({placeholders})
    ) AS errores
    GROUP BY kardex_esc
"""

RANKING_SQL = """
    SELECT responsable, COUNT(*) AS total FROM (
        SELECT TRIM(k.responsable_new) AS responsable
        FROM kardex AS k
        INNER JOIN contratantes AS con ON con.kardex = k.kardex
        INNER JOIN cliente2 AS c2 ON c2.idcontratante = con.idcontratante
        INNER JOIN contratantesxacto AS cxa ON cxa.idcontratante = con.idcontratante
        LEFT JOIN renta AS re ON re.idcontratante = con.idcontratante
        WHERE cxa.parte = 1
          AND TRIM(IFNULL(k.responsable_new, '')) <> ''
          AND k.codactos = '030'
          AND (re.pregu1 IS NULL OR re.pregu2 IS NULL OR re.pregu3 IS NULL)
          AND YEAR(k.fechaescritura) = %s

        UNION ALL

        SELECT TRIM(k.responsable_new) AS responsable
        FROM kardex AS k
        LEFT JOIN detallebienes AS db ON db.kardex = k.kardex
        WHERE TRIM(IFNULL(k.responsable_new, '')) <> ''
          AND k.codactos IN ('030', '084', '033', '036', '037', '047', '024')
          AND (db.detbien IS NULL OR db.idtipbien = 0 OR db.tipob = '')
          AND YEAR(k.fechaescritura) = %s

        UNION ALL

        SELECT TRIM(k.responsable_new) AS responsable
        FROM kardex AS k
        LEFT JOIN contratantesxacto AS cxa ON cxa.kardex = k.kardex
        WHERE TRIM(IFNULL(k.responsable_new, '')) <> ''
          AND k.codactos = '094'
          AND (cxa.ofondo = '' OR cxa.ofondo IS NULL)
          AND (cxa.parte = '1' OR cxa.parte = '2')
          AND YEAR(k.fechaescritura) = %s

        UNION ALL

        SELECT TRIM(k.responsable_new) AS responsable
        FROM kardex AS k
        WHERE TRIM(IFNULL(k.responsable_new, '')) <> ''
          AND (k.fechaconclusion = '' OR k.fechaconclusion IS NULL)
          AND YEAR(k.fechaescritura) = %s
    ) AS errores
    GROUP BY responsable
    ORDER BY total DESC, responsable ASC
"""


def parse_year(raw: Any) -> int:
    try:
        year = int(str(raw or "").strip())
    except (TypeError, ValueError):
        year = date.today().year
    current = date.today().year
    if year < 2021 or year > current:
        return current
    return year


def parse_writing_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def urgency_for_writing_date(fechaescritura: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """Badge copy matches reportErrors.js (20-day window from fechaescritura)."""
    today = today or date.today()
    written = parse_writing_date(fechaescritura)
    if written is None:
        return {
            "dias": None,
            "level": "urgent",
            "label": "CORREGIR URGENTE",
            "tone": "red",
        }
    dias = (today - written).days
    if dias > 20:
        return {"dias": dias, "level": "urgent", "label": "CORREGIR URGENTE", "tone": "red"}
    if 15 < dias < 20:
        remaining = int(20 - dias)
        return {
            "dias": dias,
            "level": "warning",
            "label": f"TE QUEDAN {remaining} dias",
            "tone": "yellow",
        }
    if dias < 15:
        remaining = int(20 - dias)
        return {
            "dias": dias,
            "level": "ok",
            "label": f"QUEDAN {remaining} dias",
            "tone": "green",
        }
    return {"dias": dias, "level": "urgent", "label": "CORREGIR URGENTE", "tone": "tomato"}


def _row_dict(cursor) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _error_item(
    row: Dict[str, Any],
    *,
    kind: str,
    error: str,
    today: date,
) -> Dict[str, Any]:
    contrato = str(row.get("acto") or "").replace("/", "")
    return {
        "idkardex": row.get("id_kardex"),
        "kardex": row.get("kardex_esc") or "",
        "fechaescritura": row.get("fechaescritura") or "",
        "contrato": contrato,
        "error": error,
        "responsable": row.get("responsable") or "",
        "contratante": row.get("contratante") or "",
        "kind": kind,
        "urgencia": urgency_for_writing_date(row.get("fechaescritura"), today=today),
    }


def list_errors_for_user(usuario: str, year: int) -> Dict[str, Any]:
    today = date.today()
    login = (usuario or "").strip()
    grouped: Dict[str, List[Dict[str, Any]]] = {
        "renta": [],
        "bien": [],
        "ofondo": [],
        "conclusion": [],
    }

    with connection.cursor() as cursor:
        cursor.execute(RENTA_SQL, [login, year])
        for row in _row_dict(cursor):
            contratante = (row.get("contratante") or "").strip()
            grouped["renta"].append(
                _error_item(
                    row,
                    kind="renta",
                    error=f"{contratante}- Ingrese renta de tercera categoria",
                    today=today,
                )
            )

        cursor.execute(BIEN_SQL, [login, year])
        for row in _row_dict(cursor):
            grouped["bien"].append(
                _error_item(
                    row,
                    kind="bien",
                    error="No existe bien, ingrese un bien",
                    today=today,
                )
            )

        cursor.execute(OFONDO_SQL, [login, year])
        for row in _row_dict(cursor):
            contratante = (row.get("contratante") or "").strip()
            grouped["ofondo"].append(
                _error_item(
                    row,
                    kind="ofondo",
                    error=f"{contratante}- Falta llenar el origen de los fondos",
                    today=today,
                )
            )

        cursor.execute(CONCLUSION_SQL, [login, year])
        for row in _row_dict(cursor):
            grouped["conclusion"].append(
                _error_item(
                    row,
                    kind="conclusion",
                    error="Falta concluir el instrumento con la firma de los contratantes",
                    today=today,
                )
            )

    items: List[Dict[str, Any]] = []
    for kind in ("renta", "bien", "ofondo", "conclusion"):
        items.extend(grouped[kind])

    return {
        "usuario": login,
        "year": year,
        "total": len(items),
        "counts": {kind: len(grouped[kind]) for kind in grouped},
        "renta": grouped["renta"],
        "bien": grouped["bien"],
        "ofondo": grouped["ofondo"],
        "conclusion": grouped["conclusion"],
        "list": items,
    }


PDT_KIND_LABELS = {
    "renta": "Renta de tercera categoría",
    "bien": "Bienes",
    "ofondo": "Origen de fondos",
    "conclusion": "Conclusión",
}


def _compliance_error_item(row: Dict[str, Any], *, kind: str, error: str) -> Dict[str, Any]:
    return {
        "kind": kind,
        "error_type": PDT_KIND_LABELS.get(kind, kind),
        "error_description": error,
        "error": error,
        "idkardex": row.get("id_kardex"),
        "kardex": row.get("kardex_esc") or "",
        "contrato": str(row.get("acto") or "").replace("/", ""),
        "contratante": row.get("contratante") or "",
        "responsable": row.get("responsable") or "",
        "fechaescritura": row.get("fechaescritura") or "",
    }


def list_errors_for_kardex(kardex: str) -> List[Dict[str, Any]]:
    """Four PHP checks for a single kardex (no responsable / year filter)."""
    key = str(kardex or "").strip()
    if not key:
        return []
    items: List[Dict[str, Any]] = []
    with connection.cursor() as cursor:
        cursor.execute(RENTA_BY_KARDEX_SQL, [key])
        for row in _row_dict(cursor):
            contratante = (row.get("contratante") or "").strip()
            items.append(
                _compliance_error_item(
                    row,
                    kind="renta",
                    error=f"{contratante}- Ingrese renta de tercera categoria",
                )
            )
        cursor.execute(BIEN_BY_KARDEX_SQL, [key])
        for row in _row_dict(cursor):
            items.append(
                _compliance_error_item(
                    row,
                    kind="bien",
                    error="No existe bien, ingrese un bien",
                )
            )
        cursor.execute(OFONDO_BY_KARDEX_SQL, [key])
        for row in _row_dict(cursor):
            contratante = (row.get("contratante") or "").strip()
            items.append(
                _compliance_error_item(
                    row,
                    kind="ofondo",
                    error=f"{contratante}- Falta llenar el origen de los fondos",
                )
            )
        cursor.execute(CONCLUSION_BY_KARDEX_SQL, [key])
        for row in _row_dict(cursor):
            items.append(
                _compliance_error_item(
                    row,
                    kind="conclusion",
                    error="Falta concluir el instrumento con la firma de los contratantes",
                )
            )
    return items


def count_errors_by_kardex(kardex_keys: List[str]) -> Dict[str, int]:
    """Error-row counts for many kardex (same four PHP checks)."""
    keys = [str(k).strip() for k in kardex_keys if str(k or "").strip()]
    if not keys:
        return {}
    placeholders = ",".join(["%s"] * len(keys))
    sql = COUNT_BY_KARDEX_SQL.format(placeholders=placeholders)
    params = list(keys) * 4
    counts: Dict[str, int] = {k: 0 for k in keys}
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        for kardex, total in cursor.fetchall():
            key = str(kardex or "").strip()
            if key:
                counts[key] = int(total or 0)
    return counts


def _usuario_display_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for u in Usuarios.objects.all().only("loginusuario", "prinom", "segnom", "apepat", "apemat"):
        login = (u.loginusuario or "").strip()
        if not login:
            continue
        name = " ".join(
            part
            for part in (u.prinom, u.segnom, u.apepat, u.apemat)
            if part and str(part).strip()
        ).strip()
        mapping[login.lower()] = name or login
    return mapping


def ranking_for_year(year: int) -> List[Dict[str, Any]]:
    names = _usuario_display_map()
    totals: Dict[str, int] = defaultdict(int)

    with connection.cursor() as cursor:
        cursor.execute(RANKING_SQL, [year, year, year, year])
        for responsable, total in cursor.fetchall():
            user = str(responsable or "").strip()
            if not user:
                continue
            totals[user] += int(total or 0)

    ranking = []
    for user, total in totals.items():
        ranking.append(
            {
                "user": user,
                "nombre": names.get(user.lower(), user),
                "total": total,
            }
        )
    ranking.sort(key=lambda row: (-row["total"], row["nombre"].lower()))
    return ranking
