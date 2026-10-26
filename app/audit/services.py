import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from django.db import transaction

from audit.context import get_actor, is_audit_suppressed

logger = logging.getLogger(__name__)

TABLE_KARDEX = "kardex"
TABLE_DETALLE_ACTOS = "detalle_actos_kardex"
TABLE_CLIENTE = "cliente"
TABLE_CLIENTE2 = "cliente2"
TABLE_FORMULARIO = "formulario"
TABLE_CONTRATANTES = "contratantes"
TABLE_CONTRATANTESXACTO = "contratantesxacto"
TABLE_PATRIMONIAL = "patrimonial"

HIDDEN_LOG_TABLES = frozenset()
HIDDEN_LOG_TABLE_ACTIONS = {
    TABLE_CONTRATANTESXACTO: frozenset({"create", "delete"}),
}

HIDDEN_KARDEX_LOG_FIELDS = frozenset(
    {
        "estado_sisgen",
        "idnotario",
        "visita",
        "pagado",
        "idrecogio",
        "autorizado",
        "desistido",
        "retenido",
        "codactos",
    }
)

HIDDEN_LOG_FIELDS_BY_TABLE = {
    TABLE_KARDEX: HIDDEN_KARDEX_LOG_FIELDS,
    TABLE_DETALLE_ACTOS: frozenset({"idtipoacto", "idtipkar", "kardex"}),
    TABLE_CONTRATANTESXACTO: frozenset(
        {
            "idtipoacto",
            "idtipkar",
            "kardex",
            "idcontratante",
            "item",
            "idcondicion",
            "parte",
        }
    ),
    TABLE_PATRIMONIAL: frozenset({"kardex", "idtipoacto"}),
}


def is_hidden_log(table_name: str, action: str = "") -> bool:
    if table_name in HIDDEN_LOG_TABLES:
        return True
    hidden_actions = HIDDEN_LOG_TABLE_ACTIONS.get(table_name)
    return bool(hidden_actions and action in hidden_actions)


def drop_hidden_log_fields(data: Optional[Dict[str, Any]], table_name: str = "") -> Dict[str, Any]:
    if not data:
        return {}
    hidden = HIDDEN_LOG_FIELDS_BY_TABLE.get(table_name or "")
    if not hidden:
        return dict(data)
    return {key: value for key, value in data.items() if key not in hidden}

# Tables whose instance already has a `kardex` column.
DIRECT_KARDEX_TABLES = frozenset(
    {
        "kardex",
        "detalle_actos_kardex",
        "contratantes",
        "contratantesxacto",
        "representantes",
        "patrimonial",
        "detallebienes",
        "detallemediopago",
        "detallevehicular",
        "predios",
        "renta",
    }
)


def jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return str(value)
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _norm(value: Any) -> Any:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        text = format(value, "f").rstrip("0").rstrip(".")
        return text or "0"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    text = str(value).strip()
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def drop_unchanged_log_fields(changes: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep only real diffs after type/label normalization."""
    if not changes:
        return {}
    kept: Dict[str, Any] = {}
    for key, delta in changes.items():
        if isinstance(delta, dict) and ("old" in delta or "new" in delta):
            if _norm(delta.get("old")) == _norm(delta.get("new")):
                continue
        kept[key] = delta
    return kept


def snapshot_instance(instance: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if instance is None:
        return data
    for field in instance._meta.concrete_fields:
        if field.primary_key:
            continue
        data[field.name] = jsonable(field.value_from_object(instance))
    return data


def snapshot_row(row: Optional[Dict[str, Any]], pk_name: str) -> Dict[str, Any]:
    if not row:
        return {}
    return {key: jsonable(value) for key, value in row.items() if key != pk_name}


def diff_snapshots(old: Optional[Dict[str, Any]], new: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    old = old or {}
    new = new or {}
    changes: Dict[str, Any] = {}
    for key in set(old) | set(new):
        previous = old.get(key)
        current = new.get(key)
        if _norm(previous) != _norm(current):
            changes[key] = {"old": previous, "new": current}
    return changes


def create_changes(new: Dict[str, Any]) -> Dict[str, Any]:
    return {key: {"old": None, "new": value} for key, value in new.items() if _norm(value) != ""}


def delete_changes(old: Dict[str, Any]) -> Dict[str, Any]:
    return {key: {"old": value, "new": None} for key, value in old.items() if _norm(value) != ""}


def record_pk_of(instance: Any) -> str:
    pk = getattr(instance, "pk", None)
    if pk is None:
        return ""
    return str(pk)


def resolve_kardex_codes(table_name: str, instance: Any = None, payload: Optional[Dict] = None) -> List[str]:
    """Find kardex string codes for a changed row. Safe to call from Celery."""
    payload = payload or {}
    direct = (getattr(instance, "kardex", None) if instance is not None else None) or payload.get("kardex")
    if table_name == TABLE_KARDEX:
        code = direct or payload.get("record_pk")
        return [str(code)] if code else []
    if table_name in DIRECT_KARDEX_TABLES and direct:
        return [str(direct)]

    try:
        from notaria.models import Cliente2, Contratantes, Renta
    except Exception:
        return [str(direct)] if direct else []

    if table_name == TABLE_CLIENTE2:
        pk = payload.get("record_pk") or (record_pk_of(instance) if instance is not None else "")
        if not pk:
            return []
        return list(
            Contratantes.objects.filter(idcontratante=pk)
            .exclude(kardex__isnull=True)
            .exclude(kardex="")
            .values_list("kardex", flat=True)
            .distinct()
        )

    if table_name == TABLE_CLIENTE:
        pk = payload.get("record_pk") or (record_pk_of(instance) if instance is not None else "")
        if not pk:
            return []
        contratante_ids = list(
            Cliente2.objects.filter(idcliente=pk).values_list("idcontratante", flat=True)
        )
        if not contratante_ids:
            return []
        return list(
            Contratantes.objects.filter(idcontratante__in=contratante_ids)
            .exclude(kardex__isnull=True)
            .exclude(kardex="")
            .values_list("kardex", flat=True)
            .distinct()
        )

    if table_name == TABLE_FORMULARIO:
        idrenta = payload.get("idrenta")
        if not idrenta and instance is not None:
            idrenta = getattr(instance, "idrenta", None)
        if not idrenta:
            return []
        return list(
            Renta.objects.filter(idrenta=idrenta)
            .exclude(kardex__isnull=True)
            .exclude(kardex="")
            .values_list("kardex", flat=True)
            .distinct()
        )

    return [str(direct)] if direct else []


def _idkardex_for(kardex: str) -> Optional[int]:
    if not kardex:
        return None
    try:
        from notaria.models import Kardex

        value = (
            Kardex.objects.filter(kardex=kardex)
            .values_list("idkardex", flat=True)
            .first()
        )
        return int(value) if value is not None else None
    except Exception:
        return None


def persist_kardex_change_sync(payload: Dict[str, Any]) -> int:
    """Write one log row per affected kardex. Never raises to the caller."""
    from audit.models import KardexChangeLog

    table_name = str(payload.get("table_name") or "")
    action = str(payload.get("action") or KardexChangeLog.ACTION_UPDATE)
    if is_hidden_log(table_name, action):
        return 0
    changes = drop_hidden_log_fields(payload.get("changes") or {}, table_name)
    if table_name == TABLE_KARDEX:
        from audit.labels import humanize_kardex_changes

        changes = humanize_kardex_changes(changes)
    elif table_name == TABLE_CONTRATANTES:
        from audit.labels import humanize_contratantes_changes

        changes = humanize_contratantes_changes(changes)
    elif table_name == TABLE_CONTRATANTESXACTO:
        from audit.labels import humanize_participa_changes

        changes = humanize_participa_changes(changes)
    elif table_name == TABLE_PATRIMONIAL:
        from audit.labels import humanize_patrimonial_changes

        changes = humanize_patrimonial_changes(changes)
    else:
        changes = drop_unchanged_log_fields(changes)
    if action == KardexChangeLog.ACTION_UPDATE and not changes:
        return 0
    record_pk = str(payload.get("record_pk") or "")
    user_id = payload.get("user_id")
    username = str(payload.get("username") or "")
    source = str(payload.get("source") or "")[:200]

    codes = payload.get("kardex_codes")
    if not codes:
        codes = resolve_kardex_codes(table_name, payload=payload)
    if not codes:
        codes = [str(payload.get("kardex") or "")]

    written = 0
    for code in codes:
        code = str(code or "")
        try:
            idkardex = payload.get("idkardex")
            if idkardex is None:
                idkardex = _idkardex_for(code)
            KardexChangeLog.objects.create(
                kardex=code,
                idkardex=idkardex,
                table_name=table_name,
                record_pk=record_pk,
                action=action,
                changes=changes,
                user_id=user_id,
                username=username,
                source=source,
            )
            written += 1
        except Exception:
            logger.exception("Failed to persist kardex change log for %s %s", table_name, code)
    return written


def _enqueue_now(payload: Dict[str, Any]) -> None:
    try:
        from audit.tasks import persist_kardex_change

        persist_kardex_change.delay(payload)
        return
    except Exception:
        logger.exception("Kardex audit enqueue failed; writing synchronously")
    try:
        persist_kardex_change_sync(payload)
    except Exception:
        logger.exception("Kardex audit sync persist failed")


def enqueue_kardex_change(payload: Dict[str, Any]) -> None:
    """Schedule the log write after commit. Failures never raise."""
    try:
        transaction.on_commit(lambda: _enqueue_now(payload), robust=True)
    except Exception:
        logger.exception("Kardex audit schedule failed; enqueueing immediately")
        _enqueue_now(payload)


def build_payload(
    *,
    table_name: str,
    record_pk: str,
    action: str,
    changes: Dict[str, Any],
    kardex: str = "",
    idkardex: Any = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    actor = get_actor()
    payload: Dict[str, Any] = {
        "table_name": table_name,
        "record_pk": str(record_pk or ""),
        "action": action,
        "changes": changes,
        "kardex": kardex or "",
        "idkardex": idkardex,
        "user_id": actor.get("user_id"),
        "username": actor.get("username") or "",
        "source": actor.get("source") or "",
    }
    if extra:
        payload.update(extra)
    return payload


def enqueue_instance_change(
    instance: Any,
    *,
    action: str,
    old: Optional[Dict[str, Any]] = None,
    new: Optional[Dict[str, Any]] = None,
    update_fields: Optional[Iterable[str]] = None,
) -> None:
    if is_audit_suppressed():
        return
    try:
        table_name = instance._meta.db_table
        if is_hidden_log(table_name, action):
            return
        if update_fields:
            allowed = set(update_fields)
            old = {k: v for k, v in (old or {}).items() if k in allowed}
            new = {k: v for k, v in (new or {}).items() if k in allowed}

        old = drop_hidden_log_fields(old, table_name)
        new = drop_hidden_log_fields(new, table_name)

        if action == "create":
            changes = create_changes(new or {})
        elif action == "delete":
            changes = delete_changes(old or {})
        else:
            changes = diff_snapshots(old, new)
            if not changes:
                return

        extra: Dict[str, Any] = {}
        if table_name == TABLE_FORMULARIO:
            extra["idrenta"] = getattr(instance, "idrenta", None)

        enqueue_kardex_change(
            build_payload(
                table_name=table_name,
                record_pk=record_pk_of(instance),
                action=action,
                changes=changes,
                kardex=getattr(instance, "kardex", None) or "",
                idkardex=getattr(instance, "idkardex", None),
                extra=extra,
            )
        )
    except Exception:
        logger.exception("Kardex audit capture failed")


def enqueue_manual_event(
    *,
    kardex: str,
    table_name: str,
    action: str = "update",
    record_pk: str = "",
    changes: Optional[Dict[str, Any]] = None,
    source: str = "",
) -> None:
    """Used for QuerySet.update() paths (calculate) that skip model signals."""
    try:
        payload = build_payload(
            table_name=table_name,
            record_pk=record_pk,
            action=action,
            changes=changes or {},
            kardex=kardex,
        )
        if source:
            payload["source"] = source
        payload["kardex_codes"] = [kardex] if kardex else []
        enqueue_kardex_change(payload)
    except Exception:
        logger.exception("Kardex audit manual event failed")
