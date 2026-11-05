"""
One progress tone per kardex for the list.

Same stage rules as the progress rail, loaded in bulk for the current page.
SISGEN, UIF, and PDT collectors stay on the open kardex: they repeat these
gaps and would make the list one heavy validation per row.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from notaria import models
from uif.services.load_data import _parse_act_codes

from compliance.services.contratantes_progress import (
    _label as contratante_label,
    _stage_status,
    local_contratante_issues,
)
from compliance.services.instrumento_progress import (
    _ESCRITURA_FIELDS,
    _numero_missing,
    _present,
    evaluate_instrumento,
)
from compliance.services.participa_progress import (
    WITHOUT_PARTICIPA,
    _answered,
    _clean,
    _filled,
    _instrument_closed,
    _label as participa_label,
    _latest_renta,
    _monto_missing,
    _yes,
    evaluate_participa,
)
from compliance.services.patrimonial_progress import (
    PDT_BIEN_ACTS,
    WITHOUT_PATRIMONIAL,
    _amount_missing,
    evaluate_patrimonial,
)

STAGE_POINTS = 4
ERROR_POINTS = 1
MAX_KEYS = 40

TONE_INCOMPLETE = "incomplete"
TONE_WARNING = "warning"
TONE_COMPLETE = "complete"


@dataclass
class KardexBundle:
    row: Any
    contratantes: list = field(default_factory=list)
    clientes: Dict[str, Any] = field(default_factory=dict)
    actos: list = field(default_factory=list)
    patrimoniales: list = field(default_factory=list)
    medios: list = field(default_factory=list)
    bienes: list = field(default_factory=list)
    rentas: list = field(default_factory=list)
    formularios: Dict[str, Any] = field(default_factory=dict)
    tipos: Dict[str, Any] = field(default_factory=dict)
    valid_ubigeo: set = field(default_factory=set)
    has_document: bool = False


def list_tone(leaves: Iterable[str], error_count: int, warning_count: int) -> str:
    """Match the rail: 100% needs every leaf finished and zero errors."""
    leaf_list = list(leaves)
    done = sum(1 for status in leaf_list if status in ("done", "warning"))
    maximum = len(leaf_list) * STAGE_POINTS + error_count * ERROR_POINTS
    earned = done * STAGE_POINTS
    raw = 0 if maximum == 0 else int((earned / maximum) * 100 + 0.5)
    percent = min(raw, 99) if error_count else raw
    if error_count or percent < 100:
        return TONE_INCOMPLETE
    if warning_count:
        return TONE_WARNING
    return TONE_COMPLETE


def score_bundle(bundle: KardexBundle) -> str:
    leaves: List[str] = []
    errors = 0
    warnings = 0

    status, error_n, warning_n = _contratantes(bundle)
    leaves.append(status)
    errors += error_n
    warnings += warning_n

    tip = _tip(bundle.row)
    if tip not in WITHOUT_PATRIMONIAL:
        patri_errors, patri_leaves = _patrimonial(bundle)
        errors += patri_errors
        leaves.extend(patri_leaves)
    if tip not in WITHOUT_PARTICIPA:
        part_errors, part_warnings, part_leaves = _participa(bundle)
        errors += part_errors
        warnings += part_warnings
        leaves.extend(part_leaves)

    inst_errors, inst_leaves = _instrumento(bundle)
    errors += inst_errors
    leaves.extend(inst_leaves)
    return list_tone(leaves, errors, warnings)


class KardexListProgressService:
    def summarize(self, keys: Iterable[str]) -> Dict[str, str]:
        ordered = _keys(keys)
        if not ordered:
            return {}

        rows = list(models.Kardex.objects.filter(kardex__in=ordered))
        by_key = {_clean(row.kardex): row for row in rows}
        found = [key for key in ordered if key in by_key]
        if not found:
            return {key: TONE_INCOMPLETE for key in ordered}

        contratantes = list(models.Contratantes.objects.filter(kardex__in=found))
        actos = list(models.Contratantesxacto.objects.filter(kardex__in=found))
        person_ids = {
            _clean(row.idcontratante)
            for row in [*contratantes, *actos]
            if _clean(getattr(row, "idcontratante", ""))
        }
        clientes = {
            _clean(row.idcontratante): row
            for row in models.Cliente2.objects.filter(idcontratante__in=person_ids)
        } if person_ids else {}
        ubigeo_codes = {
            _clean(row.idubigeo) for row in clientes.values() if _clean(getattr(row, "idubigeo", ""))
        }
        valid_ubigeo = set(
            models.Ubigeo.objects.filter(coddis__in=list(ubigeo_codes)).values_list("coddis", flat=True)
        ) if ubigeo_codes else set()

        patrimoniales = list(models.Patrimonial.objects.filter(kardex__in=found))
        medios = list(models.Detallemediopago.objects.filter(kardex__in=found))
        bienes = list(models.Detallebienes.objects.filter(kardex__in=found))
        rentas = list(models.Renta.objects.filter(kardex__in=found))
        renta_ids = [_clean(row.idrenta) for row in rentas if _clean(row.idrenta)]
        formularios = {
            _clean(row.idrenta): row
            for row in models.Formulario.objects.filter(idrenta__in=renta_ids)
        } if renta_ids else {}

        act_codes = set()
        for row in rows:
            act_codes.update(_act_codes(row))
        tipos = {
            _clean(tipo.idtipoacto): tipo
            for tipo in models.Tiposdeacto.objects.filter(idtipoacto__in=act_codes)
        } if act_codes else {}
        documents = _documents(found)

        grouped = {
            "contratantes": _group(contratantes),
            "actos": _group(actos),
            "patrimoniales": _group(patrimoniales),
            "medios": _group(medios),
            "bienes": _group(bienes),
            "rentas": _group(rentas),
        }
        out: Dict[str, str] = {}
        for key in ordered:
            row = by_key.get(key)
            if row is None:
                out[key] = TONE_INCOMPLETE
                continue
            bundle = KardexBundle(
                row=row,
                contratantes=grouped["contratantes"].get(key, []),
                clientes=clientes,
                actos=grouped["actos"].get(key, []),
                patrimoniales=grouped["patrimoniales"].get(key, []),
                medios=grouped["medios"].get(key, []),
                bienes=grouped["bienes"].get(key, []),
                rentas=grouped["rentas"].get(key, []),
                formularios=formularios,
                tipos={code: tipos[code] for code in _act_codes(row) if code in tipos},
                valid_ubigeo=valid_ubigeo,
                has_document=key in documents,
            )
            out[key] = score_bundle(bundle)
        return out


def _keys(keys: Iterable[str]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for raw in keys:
        key = _clean(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
        if len(ordered) >= MAX_KEYS:
            break
    return ordered


def _group(rows: Iterable[Any]) -> Dict[str, list]:
    grouped: Dict[str, list] = defaultdict(list)
    for row in rows:
        key = _clean(getattr(row, "kardex", ""))
        if key:
            grouped[key].append(row)
    return grouped


def _documents(keys: List[str]) -> set:
    try:
        from ducumentation.models import Documentogenerados

        return set(
            Documentogenerados.objects.filter(kardex__in=keys).values_list("kardex", flat=True)
        )
    except Exception:
        return set()


def _tip(row: Any) -> int:
    try:
        return int(row.idtipkar)
    except (TypeError, ValueError):
        return 0


def _act_codes(row: Any) -> List[str]:
    return _parse_act_codes(_clean(getattr(row, "codactos", "")).replace(",", "").replace(" ", ""))


def _issue_counts(issues: List[Dict[str, str]]) -> tuple:
    errors = sum(1 for item in issues if item.get("level") == "error")
    warnings = sum(1 for item in issues if item.get("level") == "warning")
    return errors, warnings


def _contratantes(bundle: KardexBundle) -> tuple:
    if not bundle.contratantes:
        return "idle", 0, 0

    issues: List[Dict[str, str]] = []
    for row in bundle.contratantes:
        cid = _clean(row.idcontratante)
        cliente = bundle.clientes.get(cid)
        code = _clean(cliente.idubigeo) if cliente else ""
        try:
            idtipdoc = int(cliente.idtipdoc or 0) if cliente else 0
        except (TypeError, ValueError):
            idtipdoc = 0
        issues.extend(
            local_contratante_issues(
                idcontratante=cid,
                label=contratante_label(cliente, cid),
                tipper=_clean(cliente.tipper) if cliente else "",
                prinom=_clean(cliente.prinom) if cliente else "",
                apepat=_clean(cliente.apepat) if cliente else "",
                razonsocial=_clean(cliente.razonsocial) if cliente else "",
                nombre=_clean(cliente.nombre) if cliente else "",
                numdoc=_clean(cliente.numdoc) if cliente else "",
                idtipdoc=idtipdoc,
                idubigeo=code,
                ubigeo_ok=bool(code) and code in bundle.valid_ubigeo,
                has_condicion=_has_condicion(bundle.actos, cid),
                has_cliente=cliente is not None,
            )
        )
        if _missing_contact(cliente):
            who = contratante_label(cliente, cid)
            issues.append(
                {
                    "source": "sisgen",
                    "level": "warning",
                    "field": "contacto",
                    "idcontratante": cid,
                    "text": (
                        f"{who}: Falta información de contacto "
                        "(registre al menos uno: telfijo, telcel o email)"
                    ),
                }
            )
    errors, warnings = _issue_counts(issues)
    return _stage_status(issues), errors, warnings


def _has_condicion(actos: list, person_id: str) -> bool:
    for acto in actos:
        if _clean(acto.idcontratante) == person_id and _clean(acto.idcondicion):
            return True
    return False


def _missing_contact(cliente: Optional[Any]) -> bool:
    if cliente is None or _clean(getattr(cliente, "tipper", "")).upper() != "N":
        return False
    return not any(
        _clean(getattr(cliente, field, "")) for field in ("telfijo", "telcel", "email")
    )


def _patrimonial(bundle: KardexBundle) -> tuple:
    row = bundle.row
    closed = _instrument_closed(row)
    if not bundle.patrimoniales and not closed:
        return 0, ["idle", "idle"]

    codes = _act_codes(row)
    tipos = bundle.tipos
    cuantia_flags = [_clean(getattr(tipo, "cuantia", "")) for tipo in tipos.values()]
    cuantia_required = any(_yes(flag) for flag in cuantia_flags) if cuantia_flags else True
    medios_required = any(_yes(getattr(tipo, "mediospago", "")) for tipo in tipos.values())
    skip_validation = bool(tipos) and all(
        _yes(getattr(tipo, "novalidapatri", "")) for tipo in tipos.values()
    )
    if skip_validation:
        return 0, ["done", "done"]

    bienes = bundle.bienes
    valid_bien = any(int(item.idtipbien or 0) != 0 and _clean(item.tipob) for item in bienes)
    incompleto = any(int(item.idtipbien or 0) == 0 or not _clean(item.tipob) for item in bienes)
    exhibe = any(
        _clean(item.exhibiomp).upper() not in {"N", "NO", "0"} for item in bundle.patrimoniales
    )
    result = evaluate_patrimonial(
        started=True,
        cuantia_required=cuantia_required,
        medios_required=medios_required,
        bien_required=any(code in PDT_BIEN_ACTS for code in codes),
        exhibe_medios=True if (not bundle.patrimoniales and medios_required) else exhibe,
        missing_moneda=(not bundle.patrimoniales and cuantia_required) or any(
            not _clean(item.idmon) or _clean(item.idmon) == "0" for item in bundle.patrimoniales
        ),
        missing_monto=(not bundle.patrimoniales and cuantia_required) or any(
            _amount_missing(item.importetrans) for item in bundle.patrimoniales
        ),
        missing_fpago=(not bundle.patrimoniales and cuantia_required) or any(
            not _clean(item.fpago) for item in bundle.patrimoniales
        ),
        missing_oportunidad=(not bundle.patrimoniales and cuantia_required) or any(
            not _clean(item.idoppago) for item in bundle.patrimoniales
        ),
        has_medio_rows=bool(bundle.medios),
        medio_sin_tipo=any(item.codmepag in (None, 0, "") for item in bundle.medios),
        medio_sin_monto=any(
            _clean(item.idmon) not in ("", "0") and _amount_missing(item.importemp)
            for item in bundle.medios
        ),
        has_valid_bien=valid_bien,
        bien_incompleto=incompleto and not valid_bien,
    )
    steps = {step["id"]: step for step in result["steps"]}
    header_errors, _ = _issue_counts(steps["patrimonial"]["issues"])
    return header_errors, [steps["medio-pago"]["status"], steps["detalle-bien"]["status"]]


def _participa(bundle: KardexBundle) -> tuple:
    row = bundle.row
    closed = _instrument_closed(row)
    started = any(_clean(item.ofondo) for item in bundle.actos) or bool(bundle.rentas)
    if not started and not closed:
        return 0, 0, ["idle"]

    codes = _act_codes(row)
    tipos = list(bundle.tipos.values())
    origen_on = any(_yes(getattr(tipo, "origenfondo", "")) for tipo in tipos)
    origen_off = bool(tipos) and not origen_on
    pdt_ofondo = "094" in codes or _clean(row.codactos) == "094"
    pdt_renta = "030" in codes or _clean(row.codactos) == "030"
    ofondo_required = pdt_ofondo or origen_on or not origen_off
    renta_by_person = _latest_renta(bundle.rentas)

    ofondo_gaps: List[str] = []
    monto_gaps: List[str] = []
    question_gaps: List[str] = []
    formulario_gaps: List[str] = []
    seen_ofondo: set = set()
    seen_monto: set = set()
    seen_renta: set = set()
    renta_required = False

    for item in bundle.actos:
        person_id = _clean(item.idcontratante)
        if not person_id:
            continue
        name = participa_label(bundle.clientes.get(person_id), person_id)
        uif = _clean(item.uif).upper()
        parte = _clean(item.parte)
        needs_ofondo = ofondo_required and (
            uif in {"O", "B"} or (pdt_ofondo and parte in {"1", "2"})
        )
        if needs_ofondo and not _clean(item.ofondo) and person_id not in seen_ofondo:
            seen_ofondo.add(person_id)
            ofondo_gaps.append(name)
        if (
            ofondo_required
            and uif in {"O", "B"}
            and _monto_missing(item.monto)
            and person_id not in seen_monto
        ):
            seen_monto.add(person_id)
            monto_gaps.append(name)

        needs_renta = _clean(item.formulario) == "1" or (pdt_renta and parte == "1")
        if not needs_renta or person_id in seen_renta:
            continue
        seen_renta.add(person_id)
        renta_required = True
        renta = renta_by_person.get(person_id)
        if renta is None or not all(
            _answered(getattr(renta, field)) for field in ("pregu1", "pregu2", "pregu3")
        ):
            question_gaps.append(name)
            continue
        if _clean(renta.pregu3) == "0":
            form = bundle.formularios.get(_clean(renta.idrenta))
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
    steps = {step["id"]: step for step in result["steps"]}
    header_errors, _ = _issue_counts(steps["participa"]["issues"])
    pregunta_errors, _ = _issue_counts(steps["preguntas-uif"]["issues"])
    return header_errors + pregunta_errors, 0, [steps["preguntas-uif"]["status"]]


def _instrumento(bundle: KardexBundle) -> tuple:
    row = bundle.row
    started = any(_present(getattr(row, name, "")) for name in _ESCRITURA_FIELDS)
    result = evaluate_instrumento(
        digitized=bundle.has_document or started,
        escritura_started=started,
        missing_numero=_numero_missing(getattr(row, "numescritura", "")),
        missing_conclusion=not _clean(getattr(row, "fechaconclusion", "")),
    )
    steps = {step["id"]: step for step in result["steps"]}
    errors, _ = _issue_counts(steps["escrituracion"]["issues"])
    return errors, [steps["digitacion"]["status"], steps["escrituracion"]["status"]]
