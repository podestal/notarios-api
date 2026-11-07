"""
Patrimonial stage for the kardex progress rail.

Nothing saved yet stays gray. Once a patrimonial row exists, gaps follow
UIF (cuantía, forma y oportunidad de pago, medios) and PDT (detalle del bien).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from notaria import models
from uif.services.load_data import _parse_act_codes

WITHOUT_PATRIMONIAL = {2, 5}
PDT_BIEN_ACTS = {"030", "084", "033", "036", "037", "047", "024"}

UIF_STEP = {
    "invalid_forma_pago": "patrimonial",
    "invalid_oportunidad_pago": "patrimonial",
    "missing_oportunidad_descripcion": "patrimonial",
    "currency_without_amount": "patrimonial",
    "invalid_monto_operacion": "patrimonial",
    "missing_medio_pago_rows": "medio-pago",
    "invalid_medio_pago_codigo": "medio-pago",
}


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


def _amount_missing(value: Any) -> bool:
    if value in (None, ""):
        return True
    try:
        return Decimal(str(value)) <= 0
    except Exception:
        return True


def _issue(step: str, field: str, text: str, source: str = "uif") -> Dict[str, str]:
    return {
        "source": source,
        "level": "error",
        "step": step,
        "field": field,
        "text": text,
    }


def evaluate_patrimonial(
    *,
    started: bool,
    medios_required: bool,
    bien_required: bool,
    exhibe_medios: bool,
    has_medio_rows: bool,
    medio_sin_tipo: bool,
    medio_sin_monto: bool,
    has_valid_bien: bool,
    bien_incompleto: bool,
) -> Dict[str, Any]:
    """
    Return parent + child statuses. Not started is idle, not an error.

    Cuantía / forma / oportunidad gaps come only from UIF and SISGEN collectors
    (same criteria as the errors panel). Empty idoppago is valid in UIF (``V``).
    """
    if not started:
        return _payload("idle", [], [], [])

    header: List[Dict[str, str]] = []

    medios: List[Dict[str, str]] = []
    medio_status = "idle"
    if has_medio_rows:
        medio_status = "done"
        if medio_sin_tipo:
            medios.append(_issue("medio-pago", "tipo", "Falta el tipo de medio de pago"))
            medio_status = "error"
        if medio_sin_monto:
            medios.append(_issue("medio-pago", "monto", "Medio de pago con moneda y sin monto"))
            medio_status = "error"
    elif medios_required and exhibe_medios:
        medios.append(_issue("medio-pago", "filas", "Falta registrar el medio de pago"))
        medio_status = "error"
    else:
        medio_status = "done"

    bienes: List[Dict[str, str]] = []
    bien_status = "idle"
    if has_valid_bien and not bien_incompleto:
        bien_status = "done"
    elif bien_incompleto:
        bienes.append(
            _issue(
                "detalle-bien",
                "tipo",
                "Complete el tipo de bien y el bien acto jurídico",
                source="pdt",
            )
        )
        bien_status = "error"
    elif bien_required:
        bienes.append(
            _issue(
                "detalle-bien",
                "bien",
                "No existe un bien válido; complete tipo de bien y bien acto jurídico",
                source="pdt",
            )
        )
        bien_status = "error"
    else:
        bien_status = "done"

    parent = "error" if header or medios or bienes else "done"
    return _payload(parent, header, medios, bienes, medio_status, bien_status)


def _payload(
    parent: str,
    header: List[Dict[str, str]],
    medios: List[Dict[str, str]],
    bienes: List[Dict[str, str]],
    medio_status: str = "idle",
    bien_status: str = "idle",
) -> Dict[str, Any]:
    steps = [
        {"id": "patrimonial", "status": parent, "issues": header},
        {"id": "medio-pago", "status": medio_status, "issues": medios},
        {"id": "detalle-bien", "status": bien_status, "issues": bienes},
    ]
    return {"status": parent, "steps": steps}


class PatrimonialProgressService:
    def build(self, kardex: str) -> Dict[str, Any]:
        key = _clean(kardex)
        if not key:
            raise LookupError("Kardex is required")

        row = models.Kardex.objects.filter(kardex=key).first()
        if not row:
            raise LookupError(f"Kardex not found: {key}")

        if row.idtipkar in WITHOUT_PATRIMONIAL:
            body = _payload("idle", [], [], [])
            body["kardex"] = key
            body["applicable"] = False
            return body

        patrimoniales = list(models.Patrimonial.objects.filter(kardex=key))
        medios = list(models.Detallemediopago.objects.filter(kardex=key))
        bienes = list(models.Detallebienes.objects.filter(kardex=key))
        closed = _instrument_closed(row)
        if not patrimoniales and not closed:
            body = _payload("idle", [], [], [])
            body["kardex"] = key
            body["applicable"] = True
            return body
        started = True

        codes = _parse_act_codes(_clean(row.codactos).replace(",", "").replace(" ", ""))
        tipos = {
            _clean(tipo.idtipoacto): tipo
            for tipo in models.Tiposdeacto.objects.filter(idtipoacto__in=codes)
        } if codes else {}
        medios_required = any(_yes(getattr(tipo, "mediospago", "")) for tipo in tipos.values())
        skip_validation = bool(tipos) and all(
            _yes(getattr(tipo, "novalidapatri", "")) for tipo in tipos.values()
        )
        bien_required = any(code in PDT_BIEN_ACTS for code in codes)
        exhibe = any(
            _clean(item.exhibiomp).upper() not in {"N", "NO", "0"}
            for item in patrimoniales
        )

        valid_bien = any(
            int(item.idtipbien or 0) != 0 and _clean(item.tipob)
            for item in bienes
        )
        incompleto = any(
            int(item.idtipbien or 0) == 0 or not _clean(item.tipob)
            for item in bienes
        )

        if skip_validation:
            result = _payload("done", [], [], [], "done", "done")
            result["kardex"] = key
            result["applicable"] = True
            return result

        result = evaluate_patrimonial(
            started=started,
            medios_required=medios_required,
            bien_required=bien_required,
            exhibe_medios=True if (not patrimoniales and medios_required) else exhibe,
            has_medio_rows=bool(medios),
            medio_sin_tipo=any(item.codmepag in (None, 0, "") for item in medios),
            medio_sin_monto=any(
                _clean(item.idmon) not in ("", "0") and _amount_missing(item.importemp)
                for item in medios
            ),
            has_valid_bien=valid_bien,
            bien_incompleto=incompleto and not valid_bien,
        )
        result = _merge_collectors(key, result)
        result["kardex"] = key
        result["applicable"] = True
        return result


def _merge_collectors(kardex: str, result: Dict[str, Any]) -> Dict[str, Any]:
    from compliance.services.pdt_collector import collect_pdt_issues
    from compliance.services.sisgen_collector import collect_sisgen_issues
    from compliance.services.uif_collector import collect_uif_issues

    by_step = {step["id"]: step for step in result["steps"]}
    seen = {_clean(issue["text"]).lower() for step in result["steps"] for issue in step["issues"]}

    def push(step_id: str, text: str, source: str) -> None:
        cleaned = _clean(text)
        if not cleaned or cleaned.lower() in seen or step_id not in by_step:
            return
        seen.add(cleaned.lower())
        by_step[step_id]["issues"].append(
            _issue(step_id, "externo", cleaned, source=source)
        )
        by_step[step_id]["status"] = "error"
        if step_id != "patrimonial":
            by_step["patrimonial"]["status"] = "error"
        result["status"] = "error"

    try:
        uif = collect_uif_issues(kardex)
    except Exception:
        uif = {}
    for item in list(uif.get("errors") or []):
        step_id = UIF_STEP.get(_clean(item.get("error_type")))
        if step_id:
            push(step_id, item.get("error_description") or "", "uif")

    try:
        pdt = collect_pdt_issues(kardex)
    except Exception:
        pdt = {}
    for item in list(pdt.get("errors") or []):
        if _clean(item.get("kind")) != "bien":
            continue
        push("detalle-bien", item.get("error") or item.get("error_description") or "", "pdt")

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
    if any(token in low for token in ("detallebien", "predio", "placa", "vehic", "tipo de bien")):
        return "detalle-bien"
    if any(token in low for token in ("detallemediopago", "medio de pago", "mediopago", "t. de pago", "tipo de fondo")):
        return "medio-pago"
    if any(token in low for token in ("cuantía", "cuantia", "moneda informada", "forma de pago", "oportunidad de pago")):
        return "patrimonial"
    return None
