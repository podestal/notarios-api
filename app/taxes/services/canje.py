from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db import connections, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from taxes.legacy_db import next_serial_id, next_serial_ids
from taxes.models import (
    Catalogos,
    Ingresos,
    IngresosDetalles,
    ItemsRecibos,
    Recibos,
)
from taxes.services.control_interno import CONTROL_INTERNO_COMPROBANTE_ID

POSTGRES_DB = "postgres"
BOLETA_COMPROBANTE_ID = 2
IGV_PORCENTAJE = Decimal("18.00")
IGV_RATE = Decimal("0.18")
TWOPLACES = Decimal("0.01")


def get_next_recibo_numero(*, serie: str, negocio_id: int, comprobante_id: int) -> int:
    current = (
        Recibos.objects.using(POSTGRES_DB)
        .filter(
            negocio_id=negocio_id,
            comprobante_id=comprobante_id,
            serie=serie,
        )
        .aggregate(max_numero=Max("numero"))["max_numero"]
    )
    return (current or 0) + 1


def _line_tax_amounts(*, cantidad: int, line_total: Decimal) -> dict:
    total = Decimal(line_total).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    subtotal = (total / (Decimal("1") + IGV_RATE)).quantize(
        TWOPLACES, rounding=ROUND_HALF_UP
    )
    igv = (total - subtotal).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    qty = Decimal(cantidad)
    return {
        "valor_unitario": subtotal / qty if cantidad else Decimal("0"),
        "precio_unitario": (total / qty).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        if cantidad
        else Decimal("0"),
        "subtotal": subtotal,
        "igv": igv,
        "total": total,
    }


def _resolve_fecha_emision(value: datetime | None) -> datetime:
    if value is None:
        return timezone.localtime().replace(tzinfo=None)
    if timezone.is_aware(value):
        return timezone.localtime(value).replace(tzinfo=None)
    return value


@transaction.atomic(using=POSTGRES_DB)
def canjear_ingreso(
    *,
    ingreso_id: int,
    usuario_id: int,
    negocio_id: int,
    comprobante_id: int,
    serie: str,
    observaciones: str = "",
    fecha_emision=None,
):
    ingreso = (
        Ingresos.objects.using(POSTGRES_DB)
        .select_for_update()
        .filter(id_ingreso=ingreso_id, negocio_id=negocio_id)
        .first()
    )
    if not ingreso:
        raise ValidationError("Ingreso no encontrado.")

    if ingreso.comprobante_id != CONTROL_INTERNO_COMPROBANTE_ID:
        raise ValidationError("Solo se puede canjear un control interno (comprobante 7).")

    if ingreso.canjeada:
        raise ValidationError("El ingreso ya fue canjeado.")

    if ingreso.anulada:
        raise ValidationError("No se puede canjear un ingreso anulado.")

    detalles = list(
        IngresosDetalles.objects.using(POSTGRES_DB).filter(ingreso_id=ingreso_id)
    )
    if not detalles:
        raise ValidationError("El ingreso no tiene líneas.")

    fecha_emision_db = _resolve_fecha_emision(fecha_emision)
    numero = get_next_recibo_numero(
        serie=serie,
        negocio_id=negocio_id,
        comprobante_id=comprobante_id,
    )

    gravada = Decimal("0")
    igv_total = Decimal("0")
    total_recibo = Decimal("0")
    item_rows = []

    for detalle in detalles:
        catalogo = Catalogos.objects.using(POSTGRES_DB).filter(
            id_catalogo=detalle.catalogo_id
        ).first()
        amounts = _line_tax_amounts(
            cantidad=detalle.cantidad,
            line_total=detalle.total,
        )
        gravada += amounts["subtotal"]
        igv_total += amounts["igv"]
        total_recibo += amounts["total"]
        item_rows.append(
            {
                "detalle": detalle,
                "catalogo": catalogo,
                "amounts": amounts,
            }
        )

    gravada = gravada.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    igv_total = igv_total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    total_recibo = total_recibo.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    recibo = Recibos.objects.using(POSTGRES_DB).create(
        id_recibo=next_serial_id("recibos", "id_recibo"),
        fecha_emision=fecha_emision_db,
        fecha_vencimiento=fecha_emision_db.date(),
        comprobante_id=comprobante_id,
        serie=serie,
        numero=numero,
        moneda_id=ingreso.moneda_id or 1,
        gravada=gravada,
        igv=igv_total,
        total=total_recibo,
        igv_porcentaje=IGV_PORCENTAJE,
        usuario_id=usuario_id,
        negocio_id=negocio_id,
        persona_id=ingreso.persona_id,
        direccion=ingreso.direccion or "",
        observaciones=observaciones or ingreso.observaciones or "",
        motivo_baja="-",
        enviada_sunat=False,
        aceptada_sunat=False,
        anulada=False,
    )

    now = timezone.localtime().replace(tzinfo=None)
    item_ids = next_serial_ids("items_recibos", "id_item", len(item_rows))
    items = []
    for index, row in enumerate(item_rows):
        detalle = row["detalle"]
        catalogo = row["catalogo"]
        amounts = row["amounts"]
        items.append(
            ItemsRecibos(
                id_item=item_ids[index],
                recibo_id=recibo.id_recibo,
                catalogo_id=detalle.catalogo_id,
                cantidad=detalle.cantidad,
                descripcion=detalle.descripcion,
                detalles=detalle.detalles or "-",
                valor_unitario=amounts["valor_unitario"],
                precio_unitario=amounts["precio_unitario"],
                subtotal=amounts["subtotal"],
                igv=amounts["igv"],
                total=amounts["total"],
                tipo_igv_id=(catalogo.tipo_igv_id if catalogo else None) or 1,
                creado=now,
                actualizado=now,
            )
        )
    ItemsRecibos.objects.using(POSTGRES_DB).bulk_create(items)

    fecha_baja = timezone.localdate()
    with connections[POSTGRES_DB].cursor() as cursor:
        cursor.execute(
            """
            UPDATE ingresos
            SET motivo_baja = %s,
                fecha_baja = %s,
                canjeada = TRUE,
                anulada = TRUE,
                recibo_id = %s
            WHERE id_ingreso = %s
            """,
            ["CANJEADA", fecha_baja, recibo.id_recibo, ingreso_id],
        )

    ingreso.motivo_baja = "CANJEADA"
    ingreso.fecha_baja = fecha_baja
    ingreso.canjeada = True
    ingreso.anulada = True
    ingreso.recibo_id = recibo.id_recibo

    return ingreso, recibo, items
