"""
Shared PDT protocolar error helpers (escrituras / garantías / vehiculares).

Error flags match Cpu/PDTClass.php so Subsanar (correct_error.php) can run.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.db import connection

from .pdt_corrections_service import PdtCorrectionService
from .pdt_error_item import (
    CATEGORY_ACTOS,
    CATEGORY_BIENES,
    CATEGORY_MEDIO_PAGO,
    CATEGORY_OTORGANTES,
    TYPE_ACT_MINUTA,
    TYPE_BIEN_DESCRIPCION,
    TYPE_BIEN_INSERT,
    TYPE_BIEN_RELINK,
    TYPE_MP_DOCUMENTOS,
    TYPE_MP_RELINK,
    TYPE_OTG_PORCENTAJE,
    TYPE_OTG_RENTA,
    TYPE_OTG_RUC,
    build_pdt_error_item,
)

# PDTClass.php arrays
ACTOS_CON_MINUTA = ("10", "04", "24", "26")
ACTOS_SIN_BIEN = ("10",)
# Missing-renta autocorrect (cat 3 / type 3) only for compra/venta-like acts in PHP
ACTOS_RENTA_CORRECTABLE = ("04", "03")
MEDIO_PAGO_CON_DOCUMENTO = ("001", "002", "003", "005", "006", "007", "012", "099")


def parse_pdt_date_range(initial_date: str, final_date: str) -> Tuple[Any, Any]:
    try:
        start = datetime.strptime(initial_date, "%d/%m/%Y").date()
        end = datetime.strptime(final_date, "%d/%m/%Y").date()
    except ValueError:
        start = datetime.strptime(initial_date, "%Y-%m-%d").date()
        end = datetime.strptime(final_date, "%Y-%m-%d").date()
    return start, end


def _ymd_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(text, fmt)
            return int(d.strftime("%Y%m%d"))
        except ValueError:
            continue
    return None


def _dmy_int(value: Any) -> Optional[int]:
    """Parse DD/MM/YYYY (or YYYY-MM-DD) to YYYYMMDD int like PHP."""
    return _ymd_int(value)


class PdtProtocolarMixin:
    FILE_TYPE_ACT = "ACT"
    FILE_TYPE_BIE = "BIE"
    FILE_TYPE_OTG = "OTG"
    FILE_TYPE_MP = "MP"
    FILE_TYPE_FORM = "FORM"

    errors: List[Dict[str, Any]]
    total_kardex: int

    def _add_error(
        self,
        *,
        kardex: str,
        id_kardex: int,
        error_item: str,
        act: str,
        file_type: str,
        writing_date: Any = None,
        id_contractor: Any = None,
        item_mp: Any = None,
        type_act: Any = None,
        category_correct: int = 0,
        type_of_correction: int = 0,
        is_correctable: bool = False,
    ) -> None:
        self.errors.append(
            build_pdt_error_item(
                kardex=kardex,
                id_kardex=id_kardex,
                error_item=error_item,
                act=act or "",
                file_type=file_type,
                type_act=type_act,
                item_mp=item_mp,
                writing_date=writing_date,
                id_contractor=id_contractor,
                category_correct=category_correct,
                type_of_correction=type_of_correction,
                is_correctable=is_correctable,
            )
        )

    def get_results(self) -> Dict[str, Any]:
        error_types = {
            "act": len([e for e in self.errors if e["fileType"] == self.FILE_TYPE_ACT]),
            "bie": len([e for e in self.errors if e["fileType"] == self.FILE_TYPE_BIE]),
            "otg": len([e for e in self.errors if e["fileType"] == self.FILE_TYPE_OTG]),
            "mp": len([e for e in self.errors if e["fileType"] == self.FILE_TYPE_MP]),
            "form": len([e for e in self.errors if e["fileType"] == self.FILE_TYPE_FORM]),
        }
        return {
            "list": self.errors,
            "totalError": len(self.errors),
            "totalRecords": self.total_kardex,
            "summary": {
                "total_kardex": self.total_kardex,
                "total_errors": len(self.errors),
                "error_breakdown": error_types,
            },
        }

    def correct_errors(self, error_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        return PdtCorrectionService().apply(error_list)

    def _validate_common_row(
        self,
        *,
        kardex: str,
        id_kardex: int,
        num_escritura: Any,
        fecha_escritura: Any,
        nminuta: Any,
        acto: str,
        acto_sunat: str,
        idtipoacto: Any,
        item_mp: Any,
        fecha_validation: int,
        exhibio_mp: Any,
        bienes_by_item: set,
        bienes_by_acto: set,
        bienes_need_desc: set,
        has_medio_by_item: set,
        has_medio_by_acto: set,
        empty_doc_medios: set,
        missing_formulario: set,
        renta_keys: set,
        porcentaje_by_parte: Dict[str, Dict[int, Decimal]],
        ruc_bad_contractors: List[Tuple[str, str]],
        missing_roles: Optional[Dict[str, Any]] = None,
        skip_bien_insert: bool = False,
        extra_bie_label: Optional[str] = None,
    ) -> None:
        acto_sunat = str(acto_sunat or "").strip()
        idtipoacto_s = str(idtipoacto or "").strip()
        item_mp_s = str(item_mp or "").strip()
        acto_name = acto or "No especificado"
        key_acto = (kardex, idtipoacto_s)
        key_item = (kardex, item_mp_s)

        if not num_escritura or str(num_escritura) == "0":
            self._add_error(
                kardex=kardex,
                id_kardex=id_kardex,
                error_item="Numero de escritura no puedo ser cero.",
                act=acto_name,
                file_type=self.FILE_TYPE_ACT,
                writing_date=fecha_escritura,
                type_act=idtipoacto_s,
            )

        if fecha_validation == 1:
            # PHP sets categoryCorrect=1 but NOT isCorrectable
            self._add_error(
                kardex=kardex,
                id_kardex=id_kardex,
                error_item=(
                    "La fecha de conclusion no puede ser menor que la fecha de escritura."
                ),
                act=acto_name,
                file_type=self.FILE_TYPE_ACT,
                writing_date=fecha_escritura,
                type_act=idtipoacto_s,
                category_correct=CATEGORY_ACTOS,
                is_correctable=False,
            )

        if acto_sunat in ACTOS_CON_MINUTA:
            fe = _ymd_int(fecha_escritura)
            fm = _dmy_int(nminuta)
            if fe is not None and fm is not None and fe < fm:
                self._add_error(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    error_item=(
                        "La fecha de suscripción de la minuta no  puede ser mayor "
                        "que la fecha de escritura."
                    ),
                    act=acto_name,
                    file_type=self.FILE_TYPE_ACT,
                    writing_date=fecha_escritura,
                    type_act=idtipoacto_s,
                    item_mp=item_mp_s,
                    category_correct=CATEGORY_ACTOS,
                    type_of_correction=TYPE_ACT_MINUTA,
                    is_correctable=True,
                )

        # Bienes (PHP skips actosunat in arrNoBienes)
        if acto_sunat and acto_sunat not in ACTOS_SIN_BIEN and not skip_bien_insert:
            if key_item in bienes_by_item:
                if key_item in bienes_need_desc:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="Ingrese una descripción Bien Acto Jurídico",
                        act=acto_name,
                        file_type=self.FILE_TYPE_BIE,
                        type_act=idtipoacto_s,
                        item_mp=item_mp_s,
                        category_correct=CATEGORY_BIENES,
                        type_of_correction=TYPE_BIEN_DESCRIPCION,
                        is_correctable=True,
                    )
            elif key_acto in bienes_by_acto:
                self._add_error(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    error_item=(
                        "Si existe bien, pero no ha sido registrado correctamente"
                    ),
                    act=acto_name,
                    file_type=self.FILE_TYPE_BIE,
                    type_act=idtipoacto_s,
                    item_mp=item_mp_s,
                    category_correct=CATEGORY_BIENES,
                    type_of_correction=TYPE_BIEN_RELINK,
                    is_correctable=True,
                )
            else:
                self._add_error(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    error_item=extra_bie_label or "No existe bien, ingrese un bien",
                    act=acto_name,
                    file_type=self.FILE_TYPE_BIE,
                    type_act=idtipoacto_s,
                    item_mp=item_mp_s,
                    category_correct=CATEGORY_BIENES,
                    type_of_correction=TYPE_BIEN_INSERT,
                    is_correctable=True,
                )

        # Medio de pago — missing row is NOT correctable in PHP; empty docs / bad itemmp are
        exhibio_flag = str(exhibio_mp or "").strip().upper()
        if exhibio_flag in ("SI", "1", "S", "TRUE", "YES"):
            if key_item not in has_medio_by_item and key_acto not in has_medio_by_acto:
                self._add_error(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    error_item="Si exhibió medio de pago, por favor ingrese el registro",
                    act=acto_name,
                    file_type=self.FILE_TYPE_MP,
                    type_act=idtipoacto_s,
                    item_mp=item_mp_s,
                )
            elif key_item not in has_medio_by_item and key_acto in has_medio_by_acto:
                self._add_error(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    error_item=(
                        "Si  existe registro de medio de pago, pero  su item de "
                        "medio de pago esta vacio."
                    ),
                    act=acto_name,
                    file_type=self.FILE_TYPE_MP,
                    type_act=idtipoacto_s,
                    item_mp=item_mp_s,
                    category_correct=CATEGORY_MEDIO_PAGO,
                    type_of_correction=TYPE_MP_RELINK,
                    is_correctable=True,
                )
            elif key_item in empty_doc_medios:
                self._add_error(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    error_item="Ingrese documentos del medio de pago.",
                    act=acto_name,
                    file_type=self.FILE_TYPE_MP,
                    type_act=idtipoacto_s,
                    item_mp=item_mp_s,
                    category_correct=CATEGORY_MEDIO_PAGO,
                    type_of_correction=TYPE_MP_DOCUMENTOS,
                    is_correctable=True,
                )

        # Formulario only when renta says tax payable is NOT zero (pregu3='0').
        # pregu3='1' → impuesto cero → no SUNAT form (matches Participa UI).
        if acto_sunat in ("04", "03") and kardex in missing_formulario:
            self._add_error(
                kardex=kardex,
                id_kardex=id_kardex,
                error_item="Falta número de formulario",
                act=acto_name,
                file_type=self.FILE_TYPE_FORM,
                type_act=idtipoacto_s,
            )

        # RUC bad on constitución (actoSunat 22)
        if acto_sunat == "22":
            for id_c, person_id in ruc_bad_contractors:
                self._add_error(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    error_item=f"{person_id},longitud de su  RUC, es incorrecto",
                    act=acto_name,
                    file_type=self.FILE_TYPE_OTG,
                    type_act=idtipoacto_s,
                    id_contractor=id_c,
                    category_correct=CATEGORY_OTORGANTES,
                    type_of_correction=TYPE_OTG_RUC,
                    is_correctable=True,
                )

        # Porcentaje != 100 per parte (PHP if / else if — one error max)
        parts = porcentaje_by_parte.get(kardex) or {}
        for parte in (1, 2):
            if parte not in parts:
                continue
            total = parts[parte]
            if f"{Decimal(total):.2f}" != "100.00":
                msg = (
                    "Asigne el porcentaje de participacion por contratante...."
                    if parte == 1
                    else "Asigne el porcentaje de participacion por contratante"
                )
                self._add_error(
                    kardex=kardex,
                    id_kardex=id_kardex,
                    error_item=msg,
                    act=acto_name,
                    file_type=self.FILE_TYPE_OTG,
                    type_act=idtipoacto_s,
                    category_correct=CATEGORY_OTORGANTES,
                    type_of_correction=TYPE_OTG_PORCENTAJE,
                    is_correctable=True,
                )
                break

        # Missing renta — PHP only autocorrects actosunat 04/03, tipper N, parte 1,
        # when detallebienes.fechaconst is present.
        if acto_sunat in ACTOS_RENTA_CORRECTABLE:
            has_fecha_adq = bool(
                (missing_roles or {}).get("has_fecha_adquisicion")
            )
            if has_fecha_adq:
                for c in (missing_roles or {}).get("renta_candidates", []):
                    # tuples from contractor_helpers; also accept dicts
                    if isinstance(c, dict):
                        id_c, person_id, parte, tipper = (
                            c["id"],
                            c.get("nombre") or "",
                            c.get("parte"),
                            c.get("tipper"),
                        )
                    else:
                        id_c, person_id, parte = c[0], c[1], c[2]
                        tipper = c[3] if len(c) > 3 else None
                    if str(tipper or "").upper() != "N":
                        continue
                    if str(parte).strip() != "1":
                        continue
                    if (kardex, str(id_c)) not in renta_keys:
                        self._add_error(
                            kardex=kardex,
                            id_kardex=id_kardex,
                            error_item=(
                                f"{person_id},Ingrese renta de tercera categoria"
                            ),
                            act=acto_name,
                            file_type=self.FILE_TYPE_OTG,
                            type_act=idtipoacto_s,
                            id_contractor=id_c,
                            category_correct=CATEGORY_OTORGANTES,
                            type_of_correction=TYPE_OTG_RENTA,
                            is_correctable=True,
                        )


def fetch_bulk_protocolar_context(cursor, kardex_list: List[str]) -> Dict[str, Any]:
    """Bulk lookups used by protocolar PDT validators."""
    if not kardex_list:
        return {
            "bienes_by_item": set(),
            "bienes_by_acto": set(),
            "bienes_need_desc": set(),
            "bienes_has_fecha_adq": set(),
            "has_medio_by_item": set(),
            "has_medio_by_acto": set(),
            "empty_doc_medios": set(),
            "missing_formulario": set(),
            "renta_keys": set(),
            "contratantes": {},
        }

    placeholders = ",".join(["%s"] * len(kardex_list))

    cursor.execute(
        f"""
        SELECT db.kardex, db.itemmp, db.idtipacto, db.oespecific, db.fechaconst, tb.codbien
        FROM detallebienes db
        LEFT JOIN tipobien tb ON tb.idtipbien = db.idtipbien
        WHERE db.kardex IN ({placeholders})
        """,
        kardex_list,
    )
    bienes_by_item = set()
    bienes_by_acto = set()
    bienes_need_desc = set()
    bienes_has_fecha_adq = set()
    for kardex, itemmp, idtipacto, oespecific, fechaconst, codbien in cursor.fetchall():
        bienes_by_item.add((kardex, str(itemmp or "").strip()))
        bienes_by_acto.add((kardex, str(idtipacto or "").strip()))
        if str(codbien or "").strip() == "99" and not str(oespecific or "").strip():
            bienes_need_desc.add((kardex, str(itemmp or "").strip()))
        if str(fechaconst or "").strip():
            bienes_has_fecha_adq.add((kardex, str(idtipacto or "").strip()))

    cursor.execute(
        f"""
        SELECT mp.kardex, mp.itemmp, mp.tipacto, mp.documentos, m.sunat
        FROM detallemediopago mp
        LEFT JOIN mediospago m ON m.codmepag = mp.codmepag
        WHERE mp.kardex IN ({placeholders})
        """,
        kardex_list,
    )
    has_medio_by_item = set()
    has_medio_by_acto = set()
    empty_doc_medios = set()
    for kardex, itemmp, tipacto, documentos, sunat_code in cursor.fetchall():
        has_medio_by_item.add((kardex, str(itemmp or "").strip()))
        has_medio_by_acto.add((kardex, str(tipacto or "").strip()))
        sunat = str(sunat_code or "").strip().zfill(3)
        if sunat in MEDIO_PAGO_CON_DOCUMENTO and not str(documentos or "").strip():
            empty_doc_medios.add((kardex, str(itemmp or "").strip()))

    # Transferencias vehiculares keep the bien in detallevehicular (PDT .Bie for tipkar 3),
    # not detallebienes. Count them so protocolar does not invent "No existe bien".
    cursor.execute(
        f"""
        SELECT
            dv.kardex,
            dv.itemmp,
            dv.idtipacto,
            p.itemmp
        FROM detallevehicular dv
        LEFT JOIN patrimonial p
          ON p.kardex = dv.kardex
         AND CAST(p.idtipoacto AS CHAR) = CAST(dv.idtipacto AS CHAR)
        WHERE dv.kardex IN ({placeholders})
        """,
        kardex_list,
    )
    for kardex, itemmp, idtipacto, pat_itemmp in cursor.fetchall():
        bienes_by_acto.add((kardex, str(idtipacto or "").strip()))
        for candidate in (itemmp, pat_itemmp):
            cleaned = str(candidate or "").strip()
            if cleaned:
                bienes_by_item.add((kardex, cleaned))

    # Needs formulario when pregu3='0' (impuesto NO es cero) and no form row.
    cursor.execute(
        f"""
        SELECT DISTINCT r.kardex
        FROM renta r
        LEFT JOIN formulario f ON f.idrenta = r.idrenta
        WHERE r.kardex IN ({placeholders})
          AND TRIM(IFNULL(r.pregu3, '')) = '0'
          AND f.idformulario IS NULL
        """,
        kardex_list,
    )
    missing_formulario = {row[0] for row in cursor.fetchall()}

    cursor.execute(
        f"""
        SELECT kardex, idcontratante FROM renta WHERE kardex IN ({placeholders})
        """,
        kardex_list,
    )
    renta_keys = {
        (row[0], str(row[1] or "").strip()) for row in cursor.fetchall()
    }

    cursor.execute(
        f"""
        SELECT
            cxa.kardex,
            cxa.idcontratante,
            cxa.porcentaje,
            cxa.parte,
            c.idtipdoc,
            c.numdoc,
            c.tipper,
            CASE
                WHEN c.tipper = 'N' THEN CONCAT_WS(
                    ' ',
                    NULLIF(c.prinom, ''),
                    NULLIF(c.segnom, ''),
                    NULLIF(c.apepat, ''),
                    NULLIF(c.apemat, '')
                )
                ELSE c.razonsocial
            END AS nombre
        FROM contratantesxacto cxa
        JOIN cliente2 c ON cxa.idcontratante = c.idcontratante
        WHERE cxa.kardex IN ({placeholders})
        """,
        kardex_list,
    )
    contratantes: Dict[str, list] = {}
    for row in cursor.fetchall():
        (
            kardex,
            id_contratante,
            porcentaje,
            parte,
            idtipdoc,
            numdoc,
            tipper,
            nombre,
        ) = row
        contratantes.setdefault(kardex, []).append(
            {
                "id": str(id_contratante or "").strip(),
                "porcentaje": porcentaje,
                "parte": parte,
                "idtipdoc": idtipdoc,
                "numdoc": str(numdoc or "").strip(),
                "tipper": tipper,
                "nombre": (nombre or "").strip(),
            }
        )

    return {
        "bienes_by_item": bienes_by_item,
        "bienes_by_acto": bienes_by_acto,
        "bienes_need_desc": bienes_need_desc,
        "bienes_has_fecha_adq": bienes_has_fecha_adq,
        "has_medio_by_item": has_medio_by_item,
        "has_medio_by_acto": has_medio_by_acto,
        "empty_doc_medios": empty_doc_medios,
        "missing_formulario": missing_formulario,
        "renta_keys": renta_keys,
        "contratantes": contratantes,
    }


def contractor_helpers(contratantes_for_kardex: list) -> Dict[str, Any]:
    """Build porcentaje sums, bad RUC list, renta candidates for one kardex."""
    porcentaje_by_parte: Dict[int, Decimal] = {}
    ruc_bad: List[Tuple[str, str]] = []
    renta_candidates: List[Tuple[str, str, Any]] = []

    for c in contratantes_for_kardex:
        try:
            parte = int(str(c.get("parte") or "0").strip() or "0")
        except ValueError:
            parte = 0
        try:
            pct = Decimal(str(c.get("porcentaje") or "0").strip() or "0")
        except Exception:
            pct = Decimal("0")
        if parte in (1, 2):
            porcentaje_by_parte[parte] = porcentaje_by_parte.get(parte, Decimal("0")) + pct

        nombre = c.get("nombre") or ""
        numdoc = c.get("numdoc") or ""
        person_id = f"{nombre} ({numdoc})" if numdoc else nombre
        # PDTClass: idtipdoc 8 → oTipoDocumento '06' (RUC)
        try:
            tipdoc_id = int(c.get("idtipdoc") or 0)
        except (TypeError, ValueError):
            tipdoc_id = 0
        if tipdoc_id == 8 and len(numdoc) != 11:
            ruc_bad.append((c["id"], person_id))

        renta_candidates.append((c["id"], person_id, c.get("parte"), c.get("tipper")))

    # Normalize percentages like PHP number_format
    for parte in list(porcentaje_by_parte.keys()):
        porcentaje_by_parte[parte] = Decimal(f"{porcentaje_by_parte[parte]:.2f}")

    return {
        "porcentaje_by_parte": porcentaje_by_parte,
        "ruc_bad": ruc_bad,
        "renta_candidates": renta_candidates,
    }


PROTOCOLAR_FILE_TYPE_KIND = {
    "MP": "medio_pago",
    "BIE": "bien",
    "ACT": "acto",
    "FORM": "formulario",
    "OTG": "otorgante",
}


class _SingleKardexProtocolarValidator(PdtProtocolarMixin):
    def __init__(self) -> None:
        self.errors: List[Dict[str, Any]] = []
        self.total_kardex = 0


def list_protocolar_compliance_errors_for_kardex(kardex: str) -> List[Dict[str, Any]]:
    """
    Same protocolar PDT checks as the escrituras/garantías/vehiculares report,
    for one kardex — used by the compliance error panel / progress rail.
    """
    key = str(kardex or "").strip()
    if not key:
        return []

    validator = _SingleKardexProtocolarValidator()
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
            WHERE k.kardex = %s
            ORDER BY p.idtipoacto ASC
            """,
            [key],
        )
        rows = cursor.fetchall()
        if not rows:
            return []
        validator.total_kardex = len(rows)
        ctx = fetch_bulk_protocolar_context(cursor, [key])

    for row in rows:
        (
            kardex_key,
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
        helpers = contractor_helpers(ctx["contratantes"].get(kardex_key, []))
        idtipoacto_s = str(idtipoacto or "").strip()
        validator._validate_common_row(
            kardex=kardex_key,
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
            missing_formulario=ctx["missing_formulario"],
            renta_keys=ctx["renta_keys"],
            porcentaje_by_parte={kardex_key: helpers["porcentaje_by_parte"]},
            ruc_bad_contractors=helpers["ruc_bad"],
            missing_roles={
                "renta_candidates": helpers["renta_candidates"],
                "has_fecha_adquisicion": (kardex_key, idtipoacto_s)
                in ctx["bienes_has_fecha_adq"],
            },
        )

    out: List[Dict[str, Any]] = []
    seen: set = set()
    for err in validator.errors:
        text = str(err.get("errorItem") or "").strip()
        kind = PROTOCOLAR_FILE_TYPE_KIND.get(str(err.get("fileType") or "").strip(), "pdt")
        dedupe = f"{kind}|{text.lower()}"
        if not text or dedupe in seen:
            continue
        seen.add(dedupe)
        out.append(
            {
                "kind": kind,
                "error_type": kind,
                "error_description": text,
                "error": text,
                "idkardex": err.get("idKardex"),
                "kardex": err.get("kardex") or key,
                "contrato": err.get("act") or "",
                "contratante": "",
                "responsable": "",
                "fechaescritura": err.get("writingDate") or "",
                "file_type": err.get("fileType") or "",
                "is_correctable": bool(err.get("isCorrectable")),
                "category_correct": err.get("categoryCorrect") or 0,
                "type_of_correction": err.get("typeOfCorrection") or 0,
            }
        )
    return out
