from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from taxes.legacy_db import next_serial_id, next_serial_ids
from taxes.models import Catalogos, ItemsRecibos, Recibos, Series
from taxes.services.control_interno import BOLETA_COMPROBANTE_ID, CONTROL_INTERNO_COMPROBANTE_ID
from taxes.services.document_queryset import filter_recibos_by_fecha_emision_date
from taxes.services.xml import procesar_recibo_xml

POSTGRES_DB = "postgres"
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


def _resolve_serie_documento_modificado(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        serie_row = (
            Series.objects.using(POSTGRES_DB)
            .filter(id_serie=value)
            .values_list("serie", flat=True)
            .first()
        )
        if not serie_row:
            raise ValidationError("serie_documento_modificado no encontrada.")
        return serie_row
    return str(value).strip() or None


def resolve_comprobante_from_serie(serie: str) -> int:
    comprobante_id = (
        Series.objects.using(POSTGRES_DB)
        .filter(serie=serie)
        .values_list("comprobante_id", flat=True)
        .first()
    )
    if comprobante_id is None:
        raise ValidationError(f"Serie '{serie}' no encontrada.")
    if comprobante_id == CONTROL_INTERNO_COMPROBANTE_ID:
        raise ValidationError(
            "La serie pertenece a control interno; use POST /taxes/ingresos/control-interno/."
        )
    return comprobante_id


@transaction.atomic(using=POSTGRES_DB)
def create_recibo(
    *,
    usuario_id: int,
    negocio_id: int,
    serie: str,
    moneda_id: int,
    persona_id: int,
    direccion: str,
    lineas: list[dict],
    observaciones: str = "",
    fecha_emision=None,
    tipo_nota_credito_id: int | None = None,
    tipo_nota_debito_id: int | None = None,
    tipo_recibo_modificado_id: int | None = None,
    serie_documento_modificado=None,
    numero_documento_modificado: str | None = None,
    motivo_modificacion: str | None = None,
):
    if not lineas:
        raise ValidationError("At least one line is required.")

    comprobante_id = resolve_comprobante_from_serie(serie)

    fecha_emision_db = _resolve_fecha_emision(fecha_emision)
    numero = get_next_recibo_numero(
        serie=serie,
        negocio_id=negocio_id,
        comprobante_id=comprobante_id,
    )

    if Recibos.objects.using(POSTGRES_DB).filter(
        negocio_id=negocio_id,
        comprobante_id=comprobante_id,
        serie=serie,
        numero=numero,
    ).exists():
        raise ValidationError("El comprobante ya existe.")

    gravada = Decimal("0")
    igv_total = Decimal("0")
    total_recibo = Decimal("0")
    item_rows = []

    for linea in lineas:
        catalogo = (
            Catalogos.objects.using(POSTGRES_DB)
            .filter(id_catalogo=linea["catalogo_id"])
            .first()
        )
        amounts = _line_tax_amounts(
            cantidad=linea["cantidad"],
            line_total=linea["total"],
        )
        gravada += amounts["subtotal"]
        igv_total += amounts["igv"]
        total_recibo += amounts["total"]
        item_rows.append(
            {
                "linea": linea,
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
        moneda_id=moneda_id,
        gravada=gravada,
        igv=igv_total,
        total=total_recibo,
        igv_porcentaje=IGV_PORCENTAJE,
        usuario_id=usuario_id,
        negocio_id=negocio_id,
        persona_id=persona_id,
        direccion=direccion or "",
        observaciones=observaciones or "",
        motivo_baja="-",
        enviada_sunat=False,
        aceptada_sunat=False,
        anulada=False,
        tipo_nota_credito_id=tipo_nota_credito_id,
        tipo_nota_debito_id=tipo_nota_debito_id,
        tipo_recibo_modificado_id=tipo_recibo_modificado_id,
        serie_documento_modificado=_resolve_serie_documento_modificado(
            serie_documento_modificado
        ),
        numero_documento_modificado=numero_documento_modificado,
        motivo_modificacion=motivo_modificacion or None,
    )

    now = timezone.localtime().replace(tzinfo=None)
    item_ids = next_serial_ids("items_recibos", "id_item", len(item_rows))
    items = []
    for index, row in enumerate(item_rows):
        linea = row["linea"]
        catalogo = row["catalogo"]
        amounts = row["amounts"]
        items.append(
            ItemsRecibos(
                id_item=item_ids[index],
                recibo_id=recibo.id_recibo,
                catalogo_id=linea["catalogo_id"],
                cantidad=linea["cantidad"],
                descripcion=linea["descripcion"],
                detalles=linea.get("detalles") or "-",
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
    procesar_recibo_xml(recibo.id_recibo)

    return recibo, items


def boletas_pendientes_sunat_queryset(*, negocio_id: int, fecha_emision):
    qs = (
        Recibos.objects.using(POSTGRES_DB)
        .filter(
            negocio_id=negocio_id,
            comprobante_id=BOLETA_COMPROBANTE_ID,
            enviada_sunat=False,
        )
        .exclude(anulada=True)
        .order_by("serie", "numero", "id_recibo")
    )
    return filter_recibos_by_fecha_emision_date(qs, fecha_emision)
