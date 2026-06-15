from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from taxes.legacy_db import next_serial_id, POSTGRES_DB
from taxes.services.document_queryset import filter_recibos_by_fecha_emision_date
from taxes.models import Bajas, Recibos
from taxes.services.control_interno import (
    FACTURA_COMPROBANTE_ID,
    NOTA_CREDITO_COMPROBANTE_ID,
    NOTA_DEBITO_COMPROBANTE_ID,
)

BAJA_COMPROBANTE_IDS = (
    FACTURA_COMPROBANTE_ID,
    NOTA_CREDITO_COMPROBANTE_ID,
    NOTA_DEBITO_COMPROBANTE_ID,
)


def get_next_baja_lote(*, fecha_baja) -> int:
    current = (
        Bajas.objects.using(POSTGRES_DB)
        .filter(fecha_baja=fecha_baja)
        .aggregate(total=Count("id_baja"))["total"]
        or 0
    )
    return current + 1


@transaction.atomic(using=POSTGRES_DB)
def create_baja(
    *,
    fecha_emision,
    comprobante_id: int,
    recibo_ids: list[int],
    motivo: str,
    usuario_id: int,
    negocio_id: int,
):
    if comprobante_id not in BAJA_COMPROBANTE_IDS:
        raise ValidationError(
            "La comunicación de baja solo aplica a facturas y notas de crédito/débito."
        )
    if not recibo_ids:
        raise ValidationError("At least one recibo is required.")

    recibos = list(
        Recibos.objects.using(POSTGRES_DB)
        .select_for_update()
        .filter(
            id_recibo__in=recibo_ids,
            negocio_id=negocio_id,
            comprobante_id=comprobante_id,
        )
    )
    if len(recibos) != len(set(recibo_ids)):
        raise ValidationError("Uno o más recibos no son válidos para esta baja.")

    already_linked = [r.id_recibo for r in recibos if r.baja_id]
    if already_linked:
        raise ValidationError(
            f"Los recibos ya están en una baja: {', '.join(map(str, already_linked))}."
        )

    not_sent = [r.id_recibo for r in recibos if not r.enviada_sunat]
    if not_sent:
        raise ValidationError(
            f"Los recibos deben haberse enviado a SUNAT antes de la baja: "
            f"{', '.join(map(str, not_sent))}."
        )

    fecha_baja = timezone.localdate()
    baja = Bajas.objects.using(POSTGRES_DB).create(
        id_baja=next_serial_id("bajas", "id_baja"),
        fecha_baja=fecha_baja,
        fecha_emision=fecha_emision,
        lote=get_next_baja_lote(fecha_baja=fecha_baja),
        cantidad=len(recibo_ids),
        usuario_id=usuario_id,
        enviada_sunat=False,
        aceptada_sunat=False,
    )

    motivo_value = (motivo or "-").strip() or "-"
    Recibos.objects.using(POSTGRES_DB).filter(id_recibo__in=recibo_ids).update(
        baja_id=baja.id_baja,
        anulada=True,
        motivo_baja=motivo_value,
        aceptada_sunat=False,
        enviada_sunat=False,
        resumen_id=None,
    )

    for recibo in recibos:
        recibo.baja_id = baja.id_baja
        recibo.anulada = True
        recibo.motivo_baja = motivo_value
        recibo.aceptada_sunat = False
        recibo.enviada_sunat = False
        recibo.resumen_id = None

    return baja, recibos


def anular_boleta_recibo(*, recibo: Recibos, motivo: str) -> Recibos:
    motivo_value = (motivo or "-").strip() or "-"
    fecha_baja = timezone.localdate()
    Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo.id_recibo).update(
        anulada=True,
        motivo_baja=motivo_value,
        fecha_baja=fecha_baja,
        aceptada_sunat=False,
        enviada_sunat=False,
        resumen_id=None,
    )
    return Recibos.objects.using(POSTGRES_DB).get(pk=recibo.id_recibo)


def recibos_pendientes_baja_queryset(
    *,
    negocio_id: int,
    comprobante_id: int = FACTURA_COMPROBANTE_ID,
    fecha_emision=None,
):
    qs = (
        Recibos.objects.using(POSTGRES_DB)
        .filter(
            negocio_id=negocio_id,
            comprobante_id=comprobante_id,
            baja_id__isnull=True,
            enviada_sunat=True,
        )
        .exclude(anulada=True)
        .order_by("-fecha_emision", "-id_recibo")
    )
    if fecha_emision is not None:
        qs = filter_recibos_by_fecha_emision_date(qs, fecha_emision)
    return qs


def recibos_anulados_queryset(
    *,
    negocio_id: int,
    comprobante_id: int,
):
    return (
        Recibos.objects.using(POSTGRES_DB)
        .filter(
            negocio_id=negocio_id,
            comprobante_id=comprobante_id,
            anulada=True,
        )
        .order_by("-fecha_baja", "-id_recibo")
    )
