from django.db import transaction
from django.db.models import Count
from rest_framework.exceptions import ValidationError

from taxes.legacy_db import next_serial_id, POSTGRES_DB
from taxes.models import Recibos, Resumenes

BOLETA_COMPROBANTE_ID = 2


def get_next_resumen_lote() -> int:
    current = (
        Resumenes.objects.using(POSTGRES_DB).aggregate(total=Count("id_resumen"))["total"]
        or 0
    )
    return current + 1


@transaction.atomic(using=POSTGRES_DB)
def create_resumen(
    *,
    fecha_resumen,
    fecha_emision,
    comprobante_id: int,
    recibo_ids: list[int],
    usuario_id: int,
    negocio_id: int,
):
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
        raise ValidationError("Uno o más recibos no son válidos para este resumen.")

    already_linked = [r.id_recibo for r in recibos if r.resumen_id]
    if already_linked:
        raise ValidationError(
            f"Los recibos ya están en un resumen: {', '.join(map(str, already_linked))}."
        )

    if comprobante_id != BOLETA_COMPROBANTE_ID:
        anulados = [r.id_recibo for r in recibos if r.anulada]
        if anulados:
            raise ValidationError(
                f"No se pueden incluir recibos anulados: {', '.join(map(str, anulados))}."
            )

    resumen = Resumenes.objects.using(POSTGRES_DB).create(
        id_resumen=next_serial_id("resumenes", "id_resumen"),
        fecha_resumen=fecha_resumen,
        fecha_emision=fecha_emision,
        lote=get_next_resumen_lote(),
        cantidad=len(recibo_ids),
        usuario_id=usuario_id,
        enviada_sunat=False,
        aceptada_sunat=False,
    )

    Recibos.objects.using(POSTGRES_DB).filter(id_recibo__in=recibo_ids).update(
        resumen_id=resumen.id_resumen,
        fecha_resumen=fecha_resumen,
    )

    for recibo in recibos:
        recibo.resumen_id = resumen.id_resumen
        recibo.fecha_resumen = fecha_resumen

    return resumen, recibos


def recibos_pendientes_queryset(
    *,
    negocio_id: int,
    comprobante_id: int = BOLETA_COMPROBANTE_ID,
    fecha_emision=None,
):
    qs = (
        Recibos.objects.using(POSTGRES_DB)
        .filter(
            negocio_id=negocio_id,
            comprobante_id=comprobante_id,
            resumen_id__isnull=True,
        )
        .order_by("-fecha_emision", "-id_recibo")
    )
    if fecha_emision is not None:
        qs = qs.filter(fecha_emision__date=fecha_emision)
    return qs
