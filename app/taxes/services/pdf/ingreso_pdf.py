import io
from datetime import date, datetime
from decimal import Decimal

import qrcode
from django.db import connections
from rest_framework.exceptions import NotFound

from taxes.models import Ingresos

from .numtoletras import numtoletras
from .render import render_ingreso_pdf

POSTGRES_DB = "postgres"


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        cleaned = value.strip("{}")
        if not cleaned:
            return []
        return [item.strip().strip('"') for item in cleaned.split(",")]
    return [value]


def _clean_braces(value) -> str:
    return str(value).replace("{", "").replace("}", "").strip()


def _format_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _format_time(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M:%S")
    return str(value)


def _qr_image_bytes(payload: str) -> bytes:
    image = qrcode.make(payload)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def fetch_ingreso_pdf_row(*, id_ingreso: int, negocio_id: int | None) -> dict:
    if negocio_id is not None:
        exists = Ingresos.objects.using(POSTGRES_DB).filter(
            id_ingreso=id_ingreso,
            negocio_id=negocio_id,
        ).exists()
        if not exists:
            raise NotFound("Ingreso no encontrado.")

    with connections[POSTGRES_DB].cursor() as cursor:
        cursor.execute(
            "SELECT * FROM ventas.vw_get_ingresos WHERE id_ingreso = %s",
            [id_ingreso],
        )
        row = cursor.fetchone()
        if not row:
            raise NotFound("Ingreso no encontrado.")
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))


def build_ingreso_pdf_context(row: dict) -> dict:
    cantidades = _as_list(row.get("cantidades"))
    descripciones = _as_list(row.get("descripciones"))
    precios = _as_list(row.get("precios"))
    totales = _as_list(row.get("totales"))
    detalles_item = _as_list(row.get("detalles_item"))

    lineas = []
    for index, cantidad in enumerate(cantidades):
        descripcion = _clean_braces(descripciones[index]) if index < len(descripciones) else ""
        detalle = _clean_braces(detalles_item[index]) if index < len(detalles_item) else "-"
        precio = precios[index] if index < len(precios) else ""
        total = totales[index] if index < len(totales) else ""
        lineas.append(
            {
                "cantidad": _clean_braces(cantidad),
                "descripcion": descripcion,
                "detalle": detalle,
                "precio_unitario": precio,
                "total": total,
            }
        )

    numero = str(row.get("numero") or "").zfill(8)
    total = row.get("total") or Decimal("0")
    fecha_emision = _format_date(row.get("fecha_emision"))
    hora_emision = _format_time(row.get("hora_emision"))

    qr_payload = "|".join(
        [
            str(row.get("ruc_emisor") or ""),
            str(row.get("codigo_comprobante") or ""),
            str(row.get("serie") or ""),
            numero,
            str(row.get("igv") or "0.00"),
            str(total),
            fecha_emision,
            str(row.get("tipo_documento") or ""),
            str(row.get("ruc_cliente") or ""),
            str(row.get("digest_value") or ""),
        ]
    )

    comprobante = str(row.get("comprobante") or "")

    return {
        "denominacion_emisor": row.get("denominacion_emisor") or "",
        "direccion_emisor": row.get("direccion_emisor") or "",
        "ubigeo_emisor": row.get("ubigeo_emisor") or "",
        "ruc_emisor": row.get("ruc_emisor") or "",
        "telefono": row.get("telefono") or "",
        "email": row.get("email") or "",
        "comprobante": comprobante,
        "serie": row.get("serie") or "",
        "numero": numero,
        "abr_tipo_documento": row.get("abr_tipo_documento") or "",
        "ruc_cliente": row.get("ruc_cliente") or "",
        "denominacion_cliente": row.get("denominacion_cliente") or "",
        "direccion_cliente": row.get("direccion_cliente") or "",
        "fecha_emision": fecha_emision,
        "hora_emision": hora_emision,
        "lineas": lineas,
        "total": total,
        "total_letras": numtoletras(total),
        "observaciones": row.get("observaciones") or "",
        "usuario": row.get("usuario") or "",
        "qr_image_bytes": _qr_image_bytes(qr_payload),
        "comprobante_anulado": bool(row.get("comprobante_anulado")),
    }


def generate_ingreso_pdf(*, id_ingreso: int, negocio_id: int | None) -> bytes:
    row = fetch_ingreso_pdf_row(id_ingreso=id_ingreso, negocio_id=negocio_id)
    context = build_ingreso_pdf_context(row)
    return render_ingreso_pdf(context)
