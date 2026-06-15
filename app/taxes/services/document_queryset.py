from datetime import date
from typing import Optional

from django.db.models import DateField, QuerySet
from django.db.models.functions import Cast
from django.utils.dateparse import parse_date, parse_datetime

from taxes.services.document_lookup import filter_documents_by_persona_usuario


def filter_recibos_by_fecha_emision_date(
    qs: QuerySet, fecha_emision: Optional[date]
) -> QuerySet:
    """
    Match PostgreSQL ``fecha_emision::date`` on naive local timestamps.

    ``fecha_emision__date`` with USE_TZ=True can shift the calendar day vs psql
    ``::date``; taxes recibos store naive America/Lima wall times.
    """
    if fecha_emision is None:
        return qs
    return qs.annotate(
        _fecha_emision_d=Cast("fecha_emision", output_field=DateField()),
    ).filter(_fecha_emision_d=fecha_emision)


def filter_by_fecha_emision(qs, params):
    fecha_desde = params.get("fecha_emision_desde", "").strip()
    if fecha_desde:
        date_value = parse_date(fecha_desde)
        if date_value:
            qs = qs.filter(fecha_emision__date__gte=date_value)
        else:
            parsed = parse_datetime(fecha_desde)
            if parsed:
                qs = qs.filter(fecha_emision__gte=parsed)

    fecha_hasta = params.get("fecha_emision_hasta", "").strip()
    if fecha_hasta:
        date_value = parse_date(fecha_hasta)
        if date_value:
            qs = qs.filter(fecha_emision__date__lte=date_value)
        else:
            parsed = parse_datetime(fecha_hasta)
            if parsed:
                qs = qs.filter(fecha_emision__lte=parsed)

    return qs


def apply_document_list_filters(qs, params):
    qs = filter_by_fecha_emision(qs, params)
    return filter_documents_by_persona_usuario(qs, params)
