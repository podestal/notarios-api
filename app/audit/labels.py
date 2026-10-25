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
