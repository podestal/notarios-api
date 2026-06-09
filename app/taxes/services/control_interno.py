from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from taxes.legacy_db import next_serial_id, next_serial_ids
from taxes.models import Ingresos, IngresosDetalles

CONTROL_INTERNO_COMPROBANTE_ID = 7
POSTGRES_DB = "postgres"


def get_next_numero(*, serie: str, negocio_id: int, comprobante_id: int) -> int:
    current = (
        Ingresos.objects.using(POSTGRES_DB)
        .filter(
            negocio_id=negocio_id,
            comprobante_id=comprobante_id,
            serie=serie,
        )
        .aggregate(max_numero=Max("numero"))["max_numero"]
    )
    return (current or 0) + 1


@transaction.atomic(using=POSTGRES_DB)
def create_control_interno(data, usuario_id: int, negocio_id: int):
    numero = get_next_numero(
        serie=data["serie"],
        negocio_id=negocio_id,
        comprobante_id=CONTROL_INTERNO_COMPROBANTE_ID,
    )

    ingreso = Ingresos.objects.using(POSTGRES_DB).create(
        id_ingreso=next_serial_id("ingresos", "id_ingreso"),
        comprobante_id=CONTROL_INTERNO_COMPROBANTE_ID,
        serie=data["serie"],
        numero=numero,
        fecha_emision=timezone.now(),
        moneda_id=data["moneda_id"],
        persona_id=data["persona_id"],
        direccion=data["direccion"],
        observaciones=data.get("observaciones") or "",
        total=data["total"],
        usuario_id=usuario_id,
        negocio_id=negocio_id,
        motivo_baja="-",
        recibo_id=None,
        canjeada=False,
        anulada=False,
    )

    now = timezone.now()
    detalle_ids = next_serial_ids(
        "ingresos_detalles",
        "id_ingreso_detalle",
        len(data["lineas"]),
    )
    detalles = [
        IngresosDetalles(
            id_ingreso_detalle=detalle_ids[index],
            ingreso_id=ingreso.id_ingreso,
            catalogo_id=line["catalogo_id"],
            cantidad=line["cantidad"],
            descripcion=line["descripcion"],
            detalles=line.get("detalles") or "-",
            precio_unitario=line["precio_unitario"],
            total=line["total"],
            creado=now,
            actualizado=now,
        )
        for index, line in enumerate(data["lineas"])
    ]
    IngresosDetalles.objects.using(POSTGRES_DB).bulk_create(detalles)

    return ingreso, detalles
