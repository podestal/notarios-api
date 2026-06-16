from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from taxes.models import Ingresos, IngresosDetalles
from taxes.services.control_interno import (
    BOLETA_COMPROBANTE_ID,
    CONTROL_INTERNO_COMPROBANTE_ID,
    FACTURA_COMPROBANTE_ID,
)
from taxes.services.recibo import POSTGRES_DB, create_recibo, resolve_comprobante_from_serie

ELECTRONIC_COMPROBANTE_IDS = frozenset({FACTURA_COMPROBANTE_ID, BOLETA_COMPROBANTE_ID})


@transaction.atomic(using=POSTGRES_DB)
def canjear_ingreso(
    *,
    ingreso_id: int,
    usuario_id: int,
    negocio_id: int,
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

    comprobante_id = resolve_comprobante_from_serie(serie)
    if comprobante_id not in ELECTRONIC_COMPROBANTE_IDS:
        raise ValidationError(
            "Solo se puede canjear por boleta o factura electrónica."
        )

    detalles = list(
        IngresosDetalles.objects.using(POSTGRES_DB).filter(ingreso_id=ingreso_id)
    )
    if not detalles:
        raise ValidationError("El ingreso no tiene líneas.")

    lineas = [
        {
            "catalogo_id": detalle.catalogo_id,
            "cantidad": detalle.cantidad,
            "descripcion": detalle.descripcion,
            "detalles": detalle.detalles,
            "total": detalle.total,
        }
        for detalle in detalles
    ]

    recibo, items = create_recibo(
        usuario_id=usuario_id,
        negocio_id=negocio_id,
        serie=serie,
        moneda_id=ingreso.moneda_id or 1,
        persona_id=ingreso.persona_id,
        direccion=ingreso.direccion or "",
        observaciones=observaciones or ingreso.observaciones or "",
        fecha_emision=fecha_emision,
        lineas=lineas,
        kardex=ingreso.kardex,
    )

    fecha_baja = timezone.localdate()
    ingreso.motivo_baja = "CANJEADA"
    ingreso.fecha_baja = fecha_baja
    ingreso.canjeada = True
    ingreso.anulada = True
    ingreso.recibo_id = recibo.id_recibo
    ingreso.save(
        using=POSTGRES_DB,
        update_fields=[
            "motivo_baja",
            "fecha_baja",
            "canjeada",
            "anulada",
            "recibo_id",
        ],
    )
    ingreso.refresh_from_db(using=POSTGRES_DB)

    return ingreso, recibo, items
