"""
Participa stage for the kardex progress rail.

Nothing saved yet stays gray. Once an origen de fondos or a renta row exists,
gaps follow SISGEN (origen y monto de otorgantes/beneficiarios) and PDT
(acto 094 origen, acto 030 preguntas, formulario si el impuesto no es cero).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from notaria import models
from uif.services.load_data import _parse_act_codes

WITHOUT_PARTICIPA = {2, 5}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _instrument_closed(row) -> bool:
    number = _clean(getattr(row, "numescritura", ""))
    if not number or number in {"0", "0.0", "0.00"}:
        return False
    try:
        if int(number) == 0:
            return False
    except ValueError:
        pass
    return bool(_clean(getattr(row, "fechaconclusion", "")))


def _yes(value: Any) -> bool:
    return _clean(value).upper() in {"1", "S", "SI", "Y"}


def _monto_missing(value: Any) -> bool:
    text = _clean(value).replace(",", "")
    if not text:
        return True
    try:
        return Decimal(text) <= 0
    except Exception:
        return True


def _answered(value: Any) -> bool:
    return _clean(value) in {"0", "1"}


def _filled(value: Any) -> bool:
    text = _clean(value)
    return bool(text) and text not in {"0", "0.0", "0.00"}


def _issue(step: str, field: str, text: str, source: str) -> Dict[str, str]:
    return {
        "source": source,
        "level": "error",
        "step": step,
        "field": field,
        "text": text,
    }


def sisgen_money_required(tipos: List[Any]) -> bool:
    """
    Same gate as DocumentSearchService._sisgen_skip_uif_money_checks.

    Acts in actosNOUIFSUNAT (e.g. poder 0604) do not get monto / origen de fondos
    errors in SISGEN, even when tiposdeacto.origenfondo is on.
    """
    from sisgen.sisgen_acto_xml_rules import cod_ancert_requires_uif_sunat_xml

    for tipo in tipos:
        code = _clean(getattr(tipo, "cod_ancert", None) or getattr(tipo, "codigo_ancert", None))
        if cod_ancert_requires_uif_sunat_xml(code):
            return True
    return False


def _label(cliente: Optional[models.Cliente2], idcontratante: str) -> str:
    if cliente is None:
        return f"Contratante {idcontratante}"
    if _clean(cliente.tipper).upper() == "J":
        return _clean(cliente.razonsocial) or f"Contratante {idcontratante}"
    parts = [cliente.apepat, cliente.apemat, cliente.prinom, cliente.segnom]
    name = " ".join(_clean(part) for part in parts if _clean(part))
    return name or _clean(cliente.nombre) or f"Contratante {idcontratante}"


def evaluate_participa(
    *,
    started: bool,
    ofondo_gaps: List[str],
    monto_gaps: List[str],
    renta_required: bool,
    question_gaps: List[str],
    formulario_gaps: List[str],
) -> Dict[str, Any]:
    """Return parent + preguntas UIF. Not started is idle, not an error."""
    if not started:
        return _payload("idle", [], "idle", [])

    header: List[Dict[str, str]] = []
    for name in ofondo_gaps:
        header.append(
            _issue("participa", "ofondo", f"Falta el origen de fondos de {name}", "sisgen")
        )
    for name in monto_gaps:
        header.append(
            _issue("participa", "monto", f"Monto inválido de {name}", "sisgen")
        )

    preguntas: List[Dict[str, str]] = []
    if renta_required:
        for name in question_gaps:
            preguntas.append(
                _issue(
                    "preguntas-uif",
                    "renta",
                    f"Faltan las preguntas de renta de {name}",
                    "pdt",
                )
            )
        for name in formulario_gaps:
            preguntas.append(
                _issue(
                    "preguntas-uif",
                    "formulario",
                    f"Falta el formulario de renta de {name}",
                    "pdt",
                )
            )
        preguntas_status = "error" if preguntas else "done"
    else:
        preguntas_status = "done"

    parent = "error" if header or preguntas else "done"
    return _payload(parent, header, preguntas_status, preguntas)


def _payload(
    parent: str,
    header: List[Dict[str, str]],
    preguntas_status: str,
    preguntas: List[Dict[str, str]],
) -> Dict[str, Any]:
    return {
        "status": parent,
        "steps": [
            {"id": "participa", "status": parent, "issues": header},
            {"id": "preguntas-uif", "status": preguntas_status, "issues": preguntas},
        ],
    }


class ParticipaProgressService:
    def build(self, kardex: str) -> Dict[str, Any]:
        key = _clean(kardex)
        if not key:
            raise LookupError("Kardex is required")

        row = models.Kardex.objects.filter(kardex=key).first()
        if not row:
            raise LookupError(f"Kardex not found: {key}")

        if row.idtipkar in WITHOUT_PARTICIPA:
            body = _payload("idle", [], "idle", [])
            body["kardex"] = key
            body["applicable"] = False
            return body

        actos = list(models.Contratantesxacto.objects.filter(kardex=key))
        rentas = list(models.Renta.objects.filter(kardex=key))
        started = any(_clean(item.ofondo) for item in actos) or bool(rentas)
        closed = _instrument_closed(row)
        if not started and not closed:
            body = _payload("idle", [], "idle", [])
            body["kardex"] = key
            body["applicable"] = True
            return body

        codes = _parse_act_codes(_clean(row.codactos).replace(",", "").replace(" ", ""))
        tipos = list(models.Tiposdeacto.objects.filter(idtipoacto__in=codes)) if codes else []
        money_required = sisgen_money_required(tipos)
        pdt_ofondo = "094" in codes or _clean(row.codactos) == "094"
        pdt_renta = "030" in codes or _clean(row.codactos) == "030"

        ids = {_clean(item.idcontratante) for item in actos if _clean(item.idcontratante)}
        clientes = {
            _clean(cliente.idcontratante): cliente
            for cliente in models.Cliente2.objects.filter(idcontratante__in=ids)
        } if ids else {}
        renta_by_person = _latest_renta(rentas)
        formularios = {
            _clean(item.idrenta): item
            for item in models.Formulario.objects.filter(
                idrenta__in=[_clean(item.idrenta) for item in renta_by_person.values()]
            )
        } if renta_by_person else {}

        ofondo_gaps: List[str] = []
        monto_gaps: List[str] = []
        question_gaps: List[str] = []
        formulario_gaps: List[str] = []
        seen_ofondo: set = set()
        seen_monto: set = set()
        seen_renta: set = set()
        renta_required = False

        for item in actos:
            person_id = _clean(item.idcontratante)
            if not person_id:
                continue
            name = _label(clientes.get(person_id), person_id)
            uif = _clean(item.uif).upper()
            parte = _clean(item.parte)
            needs_ofondo = (money_required and uif in {"O", "B"}) or (
                pdt_ofondo and parte in {"1", "2"}
            )
            if needs_ofondo and not _clean(item.ofondo) and person_id not in seen_ofondo:
                seen_ofondo.add(person_id)
                ofondo_gaps.append(name)
            if money_required and uif in {"O", "B"} and _monto_missing(item.monto) and person_id not in seen_monto:
                seen_monto.add(person_id)
                monto_gaps.append(name)

            needs_renta = _clean(item.formulario) == "1" or (pdt_renta and parte == "1")
            if not needs_renta or person_id in seen_renta:
                continue
            seen_renta.add(person_id)
            renta_required = True
            renta = renta_by_person.get(person_id)
            if renta is None or not all(_answered(getattr(renta, field)) for field in ("pregu1", "pregu2", "pregu3")):
                question_gaps.append(name)
                continue
            if _clean(renta.pregu3) == "0":
                form = formularios.get(_clean(renta.idrenta))
                if form is None or not _filled(form.numformu) or not _filled(form.monto):
                    formulario_gaps.append(name)

        result = evaluate_participa(
            started=True,
            ofondo_gaps=ofondo_gaps,
            monto_gaps=monto_gaps,
            renta_required=renta_required,
            question_gaps=question_gaps,
            formulario_gaps=formulario_gaps,
        )
        result = _merge_collectors(key, result)
        result["kardex"] = key
        result["applicable"] = True
        return result


def _latest_renta(rows: List[models.Renta]) -> Dict[str, models.Renta]:
    chosen: Dict[str, models.Renta] = {}
    for row in rows:
        person_id = _clean(row.idcontratante)
        if not person_id:
            continue
        current = chosen.get(person_id)
        if current is None or _renta_key(row) >= _renta_key(current):
            chosen[person_id] = row
    return chosen


def _renta_key(row: models.Renta) -> int:
    try:
        return int(_clean(row.idrenta) or 0)
    except ValueError:
        return 0


def _merge_collectors(kardex: str, result: Dict[str, Any]) -> Dict[str, Any]:
    from compliance.services.pdt_collector import collect_pdt_issues
    from compliance.services.sisgen_collector import collect_sisgen_issues

    by_step = {step["id"]: step for step in result["steps"]}
    seen = {_clean(issue["text"]).lower() for step in result["steps"] for issue in step["issues"]}

    def push(step_id: str, text: str, source: str) -> None:
        cleaned = _clean(text)
        if not cleaned or cleaned.lower() in seen or step_id not in by_step:
            return
        seen.add(cleaned.lower())
        by_step[step_id]["issues"].append(_issue(step_id, "externo", cleaned, source=source))
        by_step[step_id]["status"] = "error"
        by_step["participa"]["status"] = "error"
        result["status"] = "error"

    try:
        pdt = collect_pdt_issues(kardex)
    except Exception:
        pdt = {}
    for item in list(pdt.get("errors") or []):
        kind = _clean(item.get("kind"))
        text = item.get("error") or item.get("error_description") or ""
        if kind == "ofondo":
            push("participa", text, "pdt")
        elif kind == "renta":
            push("preguntas-uif", text, "pdt")

    try:
        sisgen = collect_sisgen_issues(kardex)
    except Exception:
        sisgen = {}
    for text in list(sisgen.get("errores") or []):
        step_id = _sisgen_step(text)
        if step_id:
            push(step_id, text, "sisgen")

    return result


def _sisgen_step(text: str) -> Optional[str]:
    low = _clean(text).lower()
    if "origen de fondo" in low or "monto inválido" in low or "monto invalido" in low:
        return "participa"
    return None
