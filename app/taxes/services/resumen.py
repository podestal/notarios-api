from django.db import transaction
from django.db.models import Count, Q
from rest_framework.exceptions import ValidationError

from taxes.legacy_db import next_serial_id, POSTGRES_DB
from taxes.models import Recibos, Resumenes
from taxes.services.control_interno import (
    BOLETA_COMPROBANTE_ID,
    NOTA_CREDITO_COMPROBANTE_ID,
    NOTA_DEBITO_COMPROBANTE_ID,
)
from taxes.services.document_queryset import filter_recibos_by_fecha_emision_date


def get_next_resumen_lote() -> int:
    current = (
        Resumenes.objects.using(POSTGRES_DB).aggregate(total=Count("id_resumen"))["total"]
        or 0
    )
    return current + 1


def _resumen_boleta_q() -> Q:
    """Boletas + NC/ND that modify boletas (same daily resumen)."""
    return Q(comprobante_id=BOLETA_COMPROBANTE_ID) | Q(
        comprobante_id__in=(NOTA_CREDITO_COMPROBANTE_ID, NOTA_DEBITO_COMPROBANTE_ID),
        tipo_recibo_modificado_id=BOLETA_COMPROBANTE_ID,
    )


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

    qs = (
        Recibos.objects.using(POSTGRES_DB)
        .select_for_update()
        .filter(id_recibo__in=recibo_ids, negocio_id=negocio_id)
    )
    if comprobante_id == BOLETA_COMPROBANTE_ID:
        qs = qs.filter(_resumen_boleta_q())
    else:
        qs = qs.filter(comprobante_id=comprobante_id)

    recibos = list(qs)
    if len(recibos) != len(set(recibo_ids)):
        raise ValidationError(
            "Uno o más recibos no son válidos para este resumen "
            "(boletas o notas de crédito/débito que modifican boleta)."
        )

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
    qs = Recibos.objects.using(POSTGRES_DB).filter(
        negocio_id=negocio_id,
        resumen_id__isnull=True,
    )
    if comprobante_id == BOLETA_COMPROBANTE_ID:
        # Daily resumen: boletas + NC/ND over boleta (not sendBill).
        qs = qs.filter(_resumen_boleta_q())
    else:
        qs = qs.filter(comprobante_id=comprobante_id)

    qs = qs.order_by("-fecha_emision", "-id_recibo")
    if fecha_emision is not None:
        qs = filter_recibos_by_fecha_emision_date(qs, fecha_emision)
    return qs
