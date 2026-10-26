from datetime import datetime
from typing import Optional

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from audit.models import KardexChangeLog
from audit.services import HIDDEN_LOG_TABLE_ACTIONS, HIDDEN_LOG_TABLES


def _parse_when(value: Optional[str]):
    if not value:
        return None
    raw = str(value).strip()
    parsed = parse_datetime(raw)
    if parsed:
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
    parsed_date = parse_date(raw)
    if parsed_date:
        return parsed_date
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def kardex_logs_queryset(params, kardex: Optional[str] = None):
    qs = KardexChangeLog.objects.all()
    hidden = Q()
    if HIDDEN_LOG_TABLES:
        hidden |= Q(table_name__in=HIDDEN_LOG_TABLES)
    for table_name, actions in HIDDEN_LOG_TABLE_ACTIONS.items():
        hidden |= Q(table_name=table_name, action__in=actions)
    if hidden:
        qs = qs.exclude(hidden)
    qs = qs.exclude(source__in=("kardex.calculate", "kardex.execute_calculation"))
    code = (kardex or params.get("kardex") or "").strip()
    if code:
        qs = qs.filter(kardex=code)

    table_name = (params.get("table") or params.get("table_name") or "").strip()
    if table_name:
        qs = qs.filter(table_name=table_name)

    action = (params.get("action") or "").strip()
    if action:
        qs = qs.filter(action=action)

    user_id = (params.get("user_id") or params.get("idusuario") or "").strip()
    if user_id:
        try:
            qs = qs.filter(user_id=int(user_id))
        except (TypeError, ValueError):
            pass

    date_from = _parse_when(params.get("dateFrom") or params.get("date_from"))
    if date_from:
        if hasattr(date_from, "hour"):
            qs = qs.filter(created_at__gte=date_from)
        else:
            qs = qs.filter(created_at__date__gte=date_from)

    date_to = _parse_when(params.get("dateTo") or params.get("date_to"))
    if date_to:
        if hasattr(date_to, "hour"):
            qs = qs.filter(created_at__lte=date_to)
        else:
            qs = qs.filter(created_at__date__lte=date_to)

    return qs
