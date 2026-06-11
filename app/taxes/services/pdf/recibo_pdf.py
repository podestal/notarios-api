from decimal import Decimal

from django.db import connections
from rest_framework.exceptions import NotFound

from taxes.models import (
    Comprobantes,
    Documentos,
    ItemsRecibos,
    Personas,
    Recibos,
    Usuarios,
)

from .common import format_date, format_time, qr_image_bytes
from .numtoletras import numtoletras
from .render import render_document_pdf

POSTGRES_DB = "postgres"


def _fetch_negocio_emisor(negocio_id: int) -> dict:
    with connections[POSTGRES_DB].cursor() as cursor:
        cursor.execute(
            """
            SELECT
                n.denominacion,
                n.direccion,
                n.ruc,
                n.email,
                n.telefono,
                COALESCE(
                    dep.descripcion || ' - ' || prov.descripcion || ' - ' || dist.descripcion,
                    ''
                ) AS ubigeo_emisor
            FROM administracion.negocios n
            LEFT JOIN administracion.sedes s ON s.negocio_id = n.id_negocio
            LEFT JOIN ubigeo.distritos dist ON dist.id_distrito = s.distrito_id
            LEFT JOIN ubigeo.provincias prov ON prov.id_provincia = dist.provincia_id
            LEFT JOIN ubigeo.departamentos dep ON dep.id_departamento = prov.departamento_id
            WHERE n.id_negocio = %s
            LIMIT 1
            """,
            [negocio_id],
        )
        row = cursor.fetchone()
        if not row:
            return {}
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))


def build_recibo_pdf_context(*, recibo: Recibos, negocio_id: int) -> dict:
    persona = Personas.objects.using(POSTGRES_DB).filter(
        id_persona=recibo.persona_id
    ).first()
    comprobante = Comprobantes.objects.using(POSTGRES_DB).filter(
        id_comprobante=recibo.comprobante_id
    ).first()
    usuario = Usuarios.objects.using(POSTGRES_DB).filter(
        id_usuario=recibo.usuario_id
    ).first()
    documento = None
    if persona:
        documento = Documentos.objects.using(POSTGRES_DB).filter(
            id_documento=persona.documento_id
        ).first()

    items = list(
        ItemsRecibos.objects.using(POSTGRES_DB)
        .filter(recibo_id=recibo.id_recibo)
        .order_by("id_item")
    )
    emisor = _fetch_negocio_emisor(negocio_id)

    lineas = [
        {
            "cantidad": item.cantidad,
            "descripcion": item.descripcion or "",
            "detalle": item.detalles or "-",
            "precio_unitario": item.precio_unitario,
            "total": item.total,
        }
        for item in items
    ]

    numero = str(recibo.numero or "").zfill(8)
    total = recibo.total or Decimal("0")
    fecha_emision = format_date(recibo.fecha_emision)
    hora_emision = format_time(recibo.fecha_emision)

    qr_payload = "|".join(
        [
            str(emisor.get("ruc") or ""),
            str(comprobante.codigo if comprobante else ""),
            str(recibo.serie or ""),
            numero,
            str(recibo.igv or "0.00"),
            str(total),
            fecha_emision,
            str(documento.codigo if documento else ""),
            str(persona.numero_documento if persona else ""),
            str(recibo.digest_value or ""),
        ]
    )

    comprobante_nombre = comprobante.descripcion if comprobante else ""

    return {
        "denominacion_emisor": emisor.get("denominacion") or "",
        "direccion_emisor": emisor.get("direccion") or "",
        "ubigeo_emisor": emisor.get("ubigeo_emisor") or "",
        "ruc_emisor": emisor.get("ruc") or "",
        "telefono": emisor.get("telefono") or "",
        "email": emisor.get("email") or "",
        "comprobante": comprobante_nombre,
        "serie": recibo.serie or "",
        "numero": numero,
        "abr_tipo_documento": (documento.abreviatura if documento else "") or "",
        "ruc_cliente": persona.numero_documento if persona else "",
        "denominacion_cliente": persona.nombre_completo if persona else "",
        "direccion_cliente": recibo.direccion or "",
        "fecha_emision": fecha_emision,
        "hora_emision": hora_emision,
        "lineas": lineas,
        "extra_totales": [
            ("OP. GRAVADA", recibo.gravada or Decimal("0")),
            ("IGV 18%", recibo.igv or Decimal("0")),
        ],
        "total": total,
        "total_letras": numtoletras(total),
        "observaciones": recibo.observaciones or "",
        "usuario": usuario.usuario if usuario else "",
        "qr_image_bytes": qr_image_bytes(qr_payload),
        "comprobante_anulado": bool(recibo.anulada),
        "leyenda_html": (
            f"Representación impresa de la <br/>{comprobante_nombre}"
        ),
    }


def generate_recibo_pdf(*, id_recibo: int, negocio_id: int | None) -> bytes:
    recibo = (
        Recibos.objects.using(POSTGRES_DB)
        .filter(id_recibo=id_recibo)
        .first()
    )
    if not recibo:
        raise NotFound("Recibo no encontrado.")
    if negocio_id is not None and recibo.negocio_id != negocio_id:
        raise NotFound("Recibo no encontrado.")

    context = build_recibo_pdf_context(
        recibo=recibo,
        negocio_id=recibo.negocio_id or negocio_id,
    )
    return render_document_pdf(context)
