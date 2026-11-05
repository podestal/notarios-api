"""
Digitación and escrituración for the kardex progress rail.

Digitación has no compliance errors: gray until a document exists, then done.
Escrituración stays gray until that section is saved. After that, the gaps are
the escritura number (UIF) and the missing conclusion (PDT).
"""

from __future__ import annotations

from typing import Any, Dict, List

from notaria import models

CONCLUSION = "Falta concluir el instrumento con la firma de los contratantes"
NUMERO = "Número de escritura faltante"

_ESCRITURA_FIELDS = (
    "numescritura",
    "fechaescritura",
    "folioini",
    "foliofin",
    "papelini",
    "papelfin",
    "numminuta",
    "fechaminuta",
    "numinstrmento",
    "txa_minuta",
    "papeltrasladoini",
    "papeltrasladofin",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _present(value: Any) -> bool:
    text = _clean(value)
    return bool(text) and text not in {"0", "0.0", "0.00"}


def _numero_missing(value: Any) -> bool:
    text = _clean(value)
    if not text:
        return True
    try:
        return int(text) == 0
    except ValueError:
        return False


def _issue(step: str, field: str, text: str, source: str) -> Dict[str, str]:
    return {
        "source": source,
        "level": "error",
        "step": step,
        "field": field,
        "text": text,
    }


def evaluate_instrumento(
    *,
    digitized: bool,
    escritura_started: bool,
    missing_numero: bool,
    missing_conclusion: bool,
) -> Dict[str, Any]:
    digitacion = {
        "id": "digitacion",
        "status": "done" if digitized else "idle",
        "issues": [],
    }
    if not escritura_started:
        escrituracion = {"id": "escrituracion", "status": "idle", "issues": []}
        parent = "idle"
    else:
        issues: List[Dict[str, str]] = []
        if missing_numero:
            issues.append(_issue("escrituracion", "numero", NUMERO, "uif"))
        if missing_conclusion:
            issues.append(_issue("escrituracion", "conclusion", CONCLUSION, "pdt"))
        status = "error" if issues else "done"
        escrituracion = {"id": "escrituracion", "status": status, "issues": issues}
        parent = status
    return {"status": parent, "steps": [digitacion, escrituracion]}


class InstrumentoProgressService:
    def build(self, kardex: str) -> Dict[str, Any]:
        key = _clean(kardex)
        if not key:
            raise LookupError("Kardex is required")

        row = models.Kardex.objects.filter(kardex=key).first()
        if not row:
            raise LookupError(f"Kardex not found: {key}")

        started = any(_present(getattr(row, field, "")) for field in _ESCRITURA_FIELDS)
        result = evaluate_instrumento(
            digitized=_has_document(key),
            escritura_started=started,
            missing_numero=_numero_missing(row.numescritura),
            missing_conclusion=not _clean(row.fechaconclusion),
        )
        if started:
            result = _merge_collectors(key, result)
        result["kardex"] = key
        return result


def _has_document(kardex: str) -> bool:
    try:
        from ducumentation.models import Documentogenerados

        return Documentogenerados.objects.filter(kardex=kardex).exists()
    except Exception:
        return False


def _merge_collectors(kardex: str, result: Dict[str, Any]) -> Dict[str, Any]:
    from compliance.services.pdt_collector import collect_pdt_issues
    from compliance.services.uif_collector import collect_uif_issues

    by_step = {step["id"]: step for step in result["steps"]}
    seen = {_clean(issue["text"]).lower() for step in result["steps"] for issue in step["issues"]}

    def push(text: str, source: str) -> None:
        cleaned = _clean(text)
        if not cleaned or cleaned.lower() in seen:
            return
        seen.add(cleaned.lower())
        by_step["escrituracion"]["issues"].append(
            _issue("escrituracion", "externo", cleaned, source)
        )
        by_step["escrituracion"]["status"] = "error"
        result["status"] = "error"

    try:
        uif = collect_uif_issues(kardex)
    except Exception:
        uif = {}
    for item in list(uif.get("errors") or []):
        if _clean(item.get("error_type")) == "missing_escritura_number":
            push(item.get("error_description") or NUMERO, "uif")

    try:
        pdt = collect_pdt_issues(kardex)
    except Exception:
        pdt = {}
    for item in list(pdt.get("errors") or []):
        if _clean(item.get("kind")) == "conclusion":
            push(item.get("error") or item.get("error_description") or CONCLUSION, "pdt")

    return result
