"""
Contratantes stage for the kardex progress rail.

Uses the same gaps SISGEN, UIF, and PDT already report for a person
(name, document, ubigeo, condición). Renta, bienes, and origen de fondos
stay on later stages.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

from notaria import models

from compliance.services.pdt_collector import collect_pdt_issues
from compliance.services.sisgen_collector import collect_sisgen_issues
from compliance.services.uif_collector import collect_uif_issues

UIF_CONTRATANTE_FIELDS = {
    "missing_nombres": "nombre",
    "missing_apellido_paterno": "nombre",
    "missing_razon_social": "nombre",
    "missing_tipo_persona": "nombre",
    "missing_tipo_documento": "documento",
    "missing_numero_documento": "documento",
    "missing_numero_ruc": "documento",
    "invalid_dni": "documento",
    "invalid_ruc": "documento",
    "nacionalidad_documento_mismatch": "documento",
    "missing_ubigeo": "ubigeo",
    "missing_departamento": "ubigeo",
    "missing_provincia": "ubigeo",
    "missing_distrito": "ubigeo",
    "missing_direccion": "direccion",
    # Representante fields live on Contratantes (inscrito / sede / partida).
    "missing_tipo_representacion": "representacion",
    "missing_persona_que_representa": "representacion",
    "missing_zona_registral": "zona_registral",
    "missing_partida_registral": "partida_registral",
}

# PDT kinds that belong to later stages, not the contratante file.
PDT_OTHER_STAGES = {
    "renta",
    "bien",
    "ofondo",
    "conclusion",
    "medio_pago",
    "acto",
    "formulario",
}

SISGEN_CONTRATANTE_RE_PARTS = (
    "contratante",
    "condici",
    "ubigeo",
    "apellido",
    "primer nombre",
    "razon social",
    "razón social",
    "documento",
    "dni",
    "direcci",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _label(cliente: Optional[models.Cliente2], idcontratante: str) -> str:
    if cliente is None:
        return f"Contratante {idcontratante}"
    if _clean(cliente.tipper).upper() == "J":
        return _clean(cliente.razonsocial) or f"Contratante {idcontratante}"
    parts = [cliente.apepat, cliente.apemat, cliente.prinom, cliente.segnom]
    name = " ".join(_clean(part) for part in parts if _clean(part))
    return name or _clean(cliente.nombre) or f"Contratante {idcontratante}"


def _bad_display_name(nombre: str) -> bool:
    letters = [char for char in nombre if char.isalpha()]
    return len(letters) < 2


def local_contratante_issues(
    *,
    idcontratante: str,
    label: str,
    tipper: str,
    prinom: str,
    apepat: str,
    razonsocial: str,
    nombre: str,
    numdoc: str,
    idtipdoc: int,
    idubigeo: str,
    ubigeo_ok: bool,
    has_condicion: bool,
    has_cliente: bool,
) -> List[Dict[str, str]]:
    """Field gaps a user can fix on the contratante, before SISGEN is sent."""
    issues: List[Dict[str, str]] = []
    who = label or f"Contratante {idcontratante}"

    def add(field: str, text: str) -> None:
        issues.append(
            {
                "source": "sisgen",
                "level": "error",
                "field": field,
                "idcontratante": idcontratante,
                "text": f"{who}: {text}",
            }
        )

    if not has_cliente:
        add("nombre", "no tiene ficha de cliente")
        if not has_condicion:
            add("condicion", "no tiene condición en ningún acto")
        return issues

    kind = tipper.upper()
    if kind == "J":
        if not razonsocial:
            add("nombre", "falta razón social")
        elif _bad_display_name(razonsocial):
            add("nombre", "la razón social no es correcta")
    elif kind == "N":
        if not prinom:
            add("nombre", "falta el primer nombre")
        if not apepat:
            add("nombre", "falta el apellido paterno")
        if nombre and _bad_display_name(nombre) and prinom and apepat:
            add("nombre", "el nombre del cliente no es correcto")
        if not numdoc:
            add("documento", "falta el número de documento")
        elif idtipdoc == 1 and (len(numdoc) != 8 or not numdoc.isdigit()):
            add("documento", "el DNI no es correcto")
    else:
        add("nombre", "tipo de persona requerido")

    if not idubigeo or not ubigeo_ok:
        add("ubigeo", "falta un ubigeo válido")

    if not has_condicion:
        add("condicion", "no tiene condición en ningún acto")

    return issues


def _sisgen_person_is_contratante(text: str) -> bool:
    lowered = text.lower()
    # Conclusion of the instrument is escrituración, even though it mentions contratantes.
    if "concluir el instrumento" in lowered or "firma de los contratantes" in lowered:
        return False
    return any(part in lowered for part in SISGEN_CONTRATANTE_RE_PARTS)


def _persona_level(text: str) -> str:
    """
    SISGEN ``personas`` are avisos in the errors panel (Personas tab), not Errores.
    Keep that level on the rail so constitution / registral / contact do not FALLÓ.
    """
    del text
    return "warning"


def _stage_status(issues: List[Dict[str, str]]) -> str:
    levels = {_clean(item.get("level")) for item in issues}
    if "error" in levels:
        return "error"
    if "warning" in levels:
        return "warning"
    return "done"


def _dedupe_key(issue: Dict[str, str]) -> str:
    return "|".join(
        [
            _clean(issue.get("idcontratante")),
            _clean(issue.get("field")),
            _clean(issue.get("text")).lower(),
        ]
    )


class ContratantesProgressService:
    def build(self, kardex: str) -> Dict[str, Any]:
        key = _clean(kardex)
        if not key:
            raise LookupError("Kardex is required")

        kardex_row = models.Kardex.objects.filter(kardex=key).first()
        if not kardex_row:
            raise LookupError(f"Kardex not found: {key}")

        contratantes = list(models.Contratantes.objects.filter(kardex=key))
        ids = [_clean(row.idcontratante) for row in contratantes if _clean(row.idcontratante)]
        clientes = {
            _clean(row.idcontratante): row
            for row in models.Cliente2.objects.filter(idcontratante__in=ids)
        }
        actos = list(models.Contratantesxacto.objects.filter(kardex=key))
        with_condicion: Set[str] = set()
        for acto in actos:
            if _clean(acto.idcondicion):
                with_condicion.add(_clean(acto.idcontratante))

        ubigeo_codes = {
            _clean(clientes[item].idubigeo)
            for item in ids
            if item in clientes and _clean(clientes[item].idubigeo)
        }
        valid_ubigeo = set(
            models.Ubigeo.objects.filter(coddis__in=list(ubigeo_codes)).values_list(
                "coddis", flat=True
            )
        ) if ubigeo_codes else set()

        if not contratantes:
            return {
                "kardex": key,
                "status": "idle",
                "count": 0,
                "issues": [],
            }

        issues: List[Dict[str, str]] = []
        for row in contratantes:
            cid = _clean(row.idcontratante)
            cliente = clientes.get(cid)
            code = _clean(cliente.idubigeo) if cliente else ""
            try:
                idtipdoc = int(cliente.idtipdoc or 0) if cliente else 0
            except (TypeError, ValueError):
                idtipdoc = 0
            issues.extend(
                local_contratante_issues(
                    idcontratante=cid,
                    label=_label(cliente, cid),
                    tipper=_clean(cliente.tipper) if cliente else "",
                    prinom=_clean(cliente.prinom) if cliente else "",
                    apepat=_clean(cliente.apepat) if cliente else "",
                    razonsocial=_clean(cliente.razonsocial) if cliente else "",
                    nombre=_clean(cliente.nombre) if cliente else "",
                    numdoc=_clean(cliente.numdoc) if cliente else "",
                    idtipdoc=idtipdoc,
                    idubigeo=code,
                    ubigeo_ok=bool(code) and code in valid_ubigeo,
                    has_condicion=cid in with_condicion,
                    has_cliente=cliente is not None,
                )
            )

        issues.extend(self._from_collectors(key, issues, kardex_row=kardex_row))
        unique = _unique(issues)
        return {
            "kardex": key,
            "status": _stage_status(unique),
            "count": len(unique),
            "issues": unique,
        }

    def _from_collectors(
        self,
        kardex: str,
        existing: List[Dict[str, str]],
        *,
        kardex_row=None,
    ) -> List[Dict[str, str]]:
        from compliance.services.sisgen_progress_gate import should_report_sisgen_issues

        seen = {_dedupe_key(item) for item in existing}
        extra: List[Dict[str, str]] = []

        def push(issue: Dict[str, str]) -> None:
            key = _dedupe_key(issue)
            if key in seen or not _clean(issue.get("text")):
                return
            seen.add(key)
            extra.append(issue)

        if should_report_sisgen_issues(kardex_row):
            try:
                sisgen = collect_sisgen_issues(kardex)
            except Exception:
                sisgen = {}
            for text in list(sisgen.get("personas") or []):
                cleaned = _clean(text)
                push(
                    {
                        "source": "sisgen",
                        "level": _persona_level(cleaned),
                        "field": _field_from_text(cleaned),
                        "idcontratante": "",
                        "text": cleaned,
                    }
                )
            for text in list(sisgen.get("errores") or []):
                if _sisgen_person_is_contratante(_clean(text)):
                    push(
                        {
                            "source": "sisgen",
                            "level": "error",
                            "field": _field_from_text(text),
                            "idcontratante": "",
                            "text": _clean(text),
                        }
                    )

        try:
            uif = collect_uif_issues(kardex)
        except Exception:
            uif = {}
        for item in list(uif.get("errors") or []):
            error_type = _clean(item.get("error_type"))
            field = UIF_CONTRATANTE_FIELDS.get(error_type)
            if not field:
                continue
            push(
                {
                    "source": "uif",
                    "level": "error",
                    "field": field,
                    "idcontratante": _clean(item.get("idContratante") or item.get("id_contratante")),
                    "text": _clean(item.get("error_description")),
                }
            )

        try:
            pdt = collect_pdt_issues(kardex)
        except Exception:
            pdt = {}
        for item in list(pdt.get("errors") or []):
            kind = _clean(item.get("kind"))
            if kind in PDT_OTHER_STAGES:
                continue
            text = _clean(item.get("error") or item.get("error_description"))
            # Protocolar OTG (RUC / %) and person-shaped mis-errores belong here.
            if kind == "otorgante" or (text and _sisgen_person_is_contratante(text)):
                push(
                    {
                        "source": "pdt",
                        "level": "error",
                        "field": _field_from_text(text),
                        "idcontratante": "",
                        "text": text,
                    }
                )
        return extra


def _field_from_text(text: str) -> str:
    lowered = text.lower()
    if "ubigeo" in lowered or "distrito" in lowered or "direcci" in lowered:
        return "ubigeo"
    if "condici" in lowered:
        return "condicion"
    if "documento" in lowered or "dni" in lowered or "ruc" in lowered:
        return "documento"
    if "nombre" in lowered or "apellido" in lowered or "razón" in lowered or "razon" in lowered:
        return "nombre"
    return "contratante"


def _unique(issues: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: Set[str] = set()
    out: List[Dict[str, str]] = []
    for issue in issues:
        key = _dedupe_key(issue)
        if key in seen:
            continue
        seen.add(key)
        out.append(issue)
    return out
