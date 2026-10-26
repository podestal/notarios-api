from typing import Any, Dict, Optional

KARDEX_FIELD_LABELS = {
    "idtipkar": "Tipo de kardex",
    "fechaingreso": "Fecha de ingreso",
    "codactos": "Actos",
    "contrato": "Contrato",
    "idusuario": "Usuario",
    "responsable": "Responsable",
    "recepcion": "Recepción",
    "fktemplate": "Plantilla",
    "kardex": "Kardex",
    "referencia": "Referencia",
    "numescritura": "Número de escritura",
    "fechaescritura": "Fecha de escritura",
    "numminuta": "Número de minuta",
    "fechaminuta": "Fecha de minuta",
    "folioini": "Folio inicial",
    "foliofin": "Folio final",
    "papelini": "Papel inicial",
    "papelfin": "Papel final",
    "papeltrasladoini": "Papel traslado inicial",
    "papeltrasladofin": "Papel traslado final",
    "fechaconclusion": "Fecha de conclusión",
    "idabogado": "Abogado",
    "nc": "NC",
}

KARDEX_USER_VALUE_FIELDS = frozenset({"idusuario", "responsable", "recepcion"})
KARDEX_LABEL_TO_FIELD = {label: field for field, label in KARDEX_FIELD_LABELS.items()}
PERSON_NAME_TABLES = frozenset({"contratantes", "cliente", "cliente2", "contratantesxacto"})
PERSON_NAME_FIELDS = ("razonsocial", "nombre", "prinom", "segnom", "apepat", "apemat")
PARTICIPA_FIELD_LABELS = {
    "monto": "Monto",
    "porcentaje": "Porcentaje",
    "ofondo": "Origen de fondos",
    "opago": "Origen de pago",
}
PATRIMONIAL_FIELD_LABELS = {
    "idmon": "Moneda",
    "fpago": "Forma de pago",
    "idoppago": "Oportunidad de pago",
}
PATRIMONIAL_LABEL_TO_FIELD = {label: field for field, label in PATRIMONIAL_FIELD_LABELS.items()}


def _as_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _user_label(value: Any, cache: Dict[str, Any]) -> Any:
    user_id = _as_int(value)
    if user_id is None:
        return value
    key = f"user:{user_id}"
    if key in cache:
        return cache[key]
    label = value
    try:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.filter(idusuario=user_id).only(
            "first_name", "last_name", "username"
        ).first()
        if user:
            name = f"{user.first_name} {user.last_name}".strip()
            label = name or user.username or value
    except Exception:
        label = value
    cache[key] = label
    return label


def _tipo_kardex_label(value: Any, cache: Dict[str, Any]) -> Any:
    tipo_id = _as_int(value)
    if tipo_id is None:
        return value
    key = f"tipokar:{tipo_id}"
    if key in cache:
        return cache[key]
    label = value
    try:
        from notaria.models import Tipokar

        name = (
            Tipokar.objects.filter(idtipkar=tipo_id)
            .values_list("nomtipkar", flat=True)
            .first()
        )
        if name:
            label = name
    except Exception:
        label = value
    cache[key] = label
    return label


def _abogado_label(value: Any, cache: Dict[str, Any]) -> Any:
    raw = str(value).strip() if value not in (None, "") else ""
    if not raw:
        return value
    key = f"abogado:{raw}"
    if key in cache:
        return cache[key]
    label = value
    try:
        from notaria.models import TbAbogado

        ids = {raw}
        padded = raw.zfill(10)
        if padded != raw:
            ids.add(padded)
        name = (
            TbAbogado.objects.filter(idabogado__in=list(ids))
            .values_list("razonsocial", flat=True)
            .first()
        )
        if name:
            label = name
    except Exception:
        label = value
    cache[key] = label
    return label


def _id_candidates(value: Any) -> list:
    raw = str(value).strip() if value not in (None, "") else ""
    if not raw:
        return []
    ids = {raw}
    if raw.isdigit():
        ids.add(raw.zfill(10))
        ids.add(str(int(raw)))
    return list(ids)


def _compose_person_name(row: Optional[Dict[str, Any]]) -> str:
    if not row:
        return ""
    razon = str(row.get("razonsocial") or "").strip()
    if razon:
        return razon
    nombre = str(row.get("nombre") or "").strip()
    if nombre:
        return nombre
    parts = [row.get("prinom"), row.get("segnom"), row.get("apepat"), row.get("apemat")]
    return " ".join(str(part).strip() for part in parts if part and str(part).strip())


def _name_from_changes(changes: Optional[Dict[str, Any]]) -> str:
    if not changes:
        return ""
    row: Dict[str, Any] = {}
    for field in PERSON_NAME_FIELDS:
        delta = changes.get(field)
        if isinstance(delta, dict) and ("old" in delta or "new" in delta):
            row[field] = delta.get("new") or delta.get("old")
        elif delta not in (None, ""):
            row[field] = delta
    return _compose_person_name(row)


def _idcontratante_from_changes(changes: Optional[Dict[str, Any]]) -> str:
    if not changes:
        return ""
    delta = changes.get("idcontratante")
    if isinstance(delta, dict) and ("old" in delta or "new" in delta):
        value = delta.get("new") or delta.get("old")
    else:
        value = delta
    return "" if value in (None, "") else str(value)


def _lookup_person_row(
    table_name: str,
    record_pk: Any,
    changes: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    try:
        from notaria.models import Cliente, Cliente2, Contratantesxacto

        values = list(PERSON_NAME_FIELDS)
        if table_name == "cliente":
            ids = _id_candidates(record_pk)
            if not ids:
                return None
            return Cliente.objects.filter(idcliente__in=ids).values(*values).first()

        idcontratante = record_pk
        if table_name == "contratantesxacto":
            idcontratante = _idcontratante_from_changes(changes)
            if not idcontratante:
                idcontratante = (
                    Contratantesxacto.objects.filter(pk=record_pk)
                    .values_list("idcontratante", flat=True)
                    .first()
                )
        ids = _id_candidates(idcontratante)
        if not ids:
            return None
        return Cliente2.objects.filter(idcontratante__in=ids).values(*values).first()
    except Exception:
        return None


def record_label_for(
    table_name: str,
    record_pk: Any,
    changes: Optional[Dict[str, Any]] = None,
    cache: Optional[Dict[str, Any]] = None,
) -> str:
    """Display name for contratante / cliente logs. Falls back to the id."""
    raw_pk = "" if record_pk in (None, "") else str(record_pk)
    if table_name not in PERSON_NAME_TABLES:
        return raw_pk
    cache = cache if cache is not None else {}
    key = f"record-label:{table_name}:{raw_pk}"
    if key in cache:
        return cache[key]

    label = _name_from_changes(changes)
    if not label:
        label = _compose_person_name(_lookup_person_row(table_name, raw_pk, changes))
    if not label:
        label = raw_pk
    cache[key] = label
    return label


def _actocondicion_name(idcondicion: Any, cache: Dict[str, Any]) -> str:
    raw = str(idcondicion).strip() if idcondicion not in (None, "") else ""
    if not raw:
        return ""
    key = f"actocondicion:{raw}"
    if key in cache:
        return cache[key]
    label = ""
    try:
        from notaria.models import Actocondicion

        name = (
            Actocondicion.objects.filter(idcondicion__in=_id_candidates(raw))
            .values_list("condicion", flat=True)
            .first()
        )
        if name:
            label = str(name).strip()
    except Exception:
        label = ""
    cache[key] = label
    return label


def _condicion_label(value: Any, cache: Dict[str, Any]) -> Any:
    if value in (None, ""):
        return value
    raw = str(value)
    key = f"condicion:{raw}"
    if key in cache:
        return cache[key]
    from notaria.utils import condicion_ids

    names = []
    for idcondicion in condicion_ids(raw):
        name = _actocondicion_name(idcondicion, cache)
        if name and name not in names:
            names.append(name)
    label = " / ".join(names) if names else value
    cache[key] = label
    return label


def humanize_contratantes_changes(
    changes: Optional[Dict[str, Any]],
    cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from audit.services import drop_unchanged_log_fields

    raw = dict(changes or {})
    if not raw:
        return {}
    cache = cache if cache is not None else {}
    labeled: Dict[str, Any] = {}
    for field, delta in raw.items():
        if field == "condicion" and isinstance(delta, dict) and ("old" in delta or "new" in delta):
            labeled[field] = {
                "old": _condicion_label(delta.get("old"), cache),
                "new": _condicion_label(delta.get("new"), cache),
            }
        elif field == "condicion":
            labeled[field] = _condicion_label(delta, cache)
        else:
            labeled[field] = delta
    return drop_unchanged_log_fields(labeled)


def _moneda_label(value: Any, cache: Dict[str, Any]) -> Any:
    if value in (None, ""):
        return value
    key = f"moneda:{value}"
    if key in cache:
        return cache[key]
    from notaria.constants import MONEDAS

    idmon = _as_int(value)
    if idmon == 0:
        label = "NO APLICA"
    else:
        meta = MONEDAS.get(idmon) if idmon is not None else None
        label = (meta or {}).get("desmon") or value
    cache[key] = label
    return label


def _fpago_label(value: Any, cache: Dict[str, Any]) -> Any:
    if value in (None, ""):
        return value
    raw = str(value).strip()
    key = f"fpago:{raw}"
    if key in cache:
        return cache[key]
    from notaria.constants import FORMAS_PAGO

    meta = FORMAS_PAGO.get(raw)
    if not meta:
        idx = _as_int(raw)
        if idx is not None:
            meta = FORMAS_PAGO.get(str(idx))
    label = (meta or {}).get("descripcion") or value
    cache[key] = label
    return label


def _oppago_label(value: Any, cache: Dict[str, Any]) -> Any:
    if value in (None, ""):
        return value
    raw = str(value).strip()
    key = f"oppago:{raw}"
    if key in cache:
        return cache[key]
    from notaria.constants import OPORTUNIDADES_PAGO

    idx = _as_int(raw)
    meta = OPORTUNIDADES_PAGO.get(idx) if idx is not None else None
    if not meta:
        for item in OPORTUNIDADES_PAGO.values():
            if str(item.get("codoppago") or "") == raw or str(item.get("idoppago")) == raw:
                meta = item
                break
    label = (meta or {}).get("desoppago") or value
    cache[key] = label
    return label


def humanize_patrimonial_value(field: str, value: Any, cache: Optional[Dict[str, Any]] = None) -> Any:
    cache = cache if cache is not None else {}
    if field == "idmon":
        return _moneda_label(value, cache)
    if field == "fpago":
        return _fpago_label(value, cache)
    if field == "idoppago":
        return _oppago_label(value, cache)
    return value


def humanize_patrimonial_changes(
    changes: Optional[Dict[str, Any]],
    cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from audit.services import drop_hidden_log_fields, drop_unchanged_log_fields

    raw = drop_hidden_log_fields(changes or {}, "patrimonial")
    if not raw:
        return {}
    cache = cache if cache is not None else {}
    labeled: Dict[str, Any] = {}
    for field, delta in raw.items():
        source_field = (
            field if field in PATRIMONIAL_FIELD_LABELS else PATRIMONIAL_LABEL_TO_FIELD.get(field, field)
        )
        label = PATRIMONIAL_FIELD_LABELS.get(source_field, field)
        if isinstance(delta, dict) and ("old" in delta or "new" in delta):
            labeled[label] = {
                "old": humanize_patrimonial_value(source_field, delta.get("old"), cache),
                "new": humanize_patrimonial_value(source_field, delta.get("new"), cache),
            }
        else:
            labeled[label] = humanize_patrimonial_value(source_field, delta, cache)
    return drop_unchanged_log_fields(labeled)


def humanize_participa_changes(
    changes: Optional[Dict[str, Any]],
    cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from audit.services import drop_hidden_log_fields, drop_unchanged_log_fields

    raw = drop_hidden_log_fields(changes or {}, "contratantesxacto")
    if not raw:
        return {}
    labeled: Dict[str, Any] = {}
    for field, delta in raw.items():
        labeled[PARTICIPA_FIELD_LABELS.get(field, field)] = delta
    return drop_unchanged_log_fields(labeled)


def _template_label(value: Any, cache: Dict[str, Any]) -> Any:
    template_id = _as_int(value)
    if template_id is None:
        return value
    key = f"template:{template_id}"
    if key in cache:
        return cache[key]
    label = value
    try:
        from notaria.models import TplTemplate

        name = (
            TplTemplate.objects.filter(pktemplate=template_id)
            .values_list("nametemplate", flat=True)
            .first()
        )
        if name:
            label = name
    except Exception:
        label = value
    cache[key] = label
    return label


def humanize_kardex_value(field: str, value: Any, cache: Optional[Dict[str, Any]] = None) -> Any:
    if value in (None, ""):
        return value
    cache = cache if cache is not None else {}
    if field == "idtipkar":
        return _tipo_kardex_label(value, cache)
    if field == "fktemplate":
        return _template_label(value, cache)
    if field == "idabogado":
        return _abogado_label(value, cache)
    if field in KARDEX_USER_VALUE_FIELDS:
        return _user_label(value, cache)
    return value


def humanize_kardex_changes(
    changes: Optional[Dict[str, Any]],
    cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from audit.services import drop_hidden_log_fields, drop_unchanged_log_fields

    raw = drop_hidden_log_fields(changes or {}, "kardex")
    if not raw:
        return {}
    if not (set(raw) & set(KARDEX_FIELD_LABELS)) and not (set(raw) & set(KARDEX_LABEL_TO_FIELD)):
        return drop_unchanged_log_fields(raw)

    cache = cache if cache is not None else {}
    labeled: Dict[str, Any] = {}
    for field, delta in raw.items():
        source_field = field if field in KARDEX_FIELD_LABELS else KARDEX_LABEL_TO_FIELD.get(field, field)
        label = KARDEX_FIELD_LABELS.get(source_field, field)
        if isinstance(delta, dict) and ("old" in delta or "new" in delta):
            labeled[label] = {
                "old": humanize_kardex_value(source_field, delta.get("old"), cache),
                "new": humanize_kardex_value(source_field, delta.get("new"), cache),
            }
        else:
            labeled[label] = humanize_kardex_value(source_field, delta, cache)
    return drop_unchanged_log_fields(labeled)
