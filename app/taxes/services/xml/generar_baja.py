from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rest_framework.exceptions import NotFound, ValidationError

from taxes.models import Bajas, Recibos
from taxes.services.control_interno import (
    FACTURA_COMPROBANTE_ID,
    NOTA_CREDITO_COMPROBANTE_ID,
    NOTA_DEBITO_COMPROBANTE_ID,
)

from .context import ReciboXmlContext, fetch_recibo_xml_context
from .generar import _load_template, _replace
from .paths import (
    POSTGRES_DB,
    baja_archivo_name,
    baja_generar_path,
    baja_serie_numero,
    ensure_output_dirs,
)


@dataclass
class BajaXmlContext:
    id_baja: int
    ruc_emisor: str
    denominacion_emisor: str
    fecha_emision: date
    fecha_comunicacion: date
    lote: int
    recibos: list[ReciboXmlContext]
    motivos_baja: dict[int, str]

    @property
    def serie_numero(self) -> str:
        return baja_serie_numero(
            fecha_comunicacion=self.fecha_comunicacion,
            lote=self.lote,
        )

    @property
    def archivo(self) -> str:
        return baja_archivo_name(
            ruc=self.ruc_emisor,
            fecha_comunicacion=self.fecha_comunicacion,
            lote=self.lote,
        )


def _build_baja_item(
    *,
    line_id: int,
    ctx: ReciboXmlContext,
    motivo_baja: str,
) -> str:
    template = _load_template("comunicacion_baja_item.xml")
    return _replace(
        template,
        {
            "item_id": str(line_id),
            "codigo_comprobante": ctx.codigo_comprobante,
            "serie": ctx.serie,
            "numero": ctx.numero_padded,
            "motivo_baja": motivo_baja or "-",
        },
    )


def fetch_baja_xml_context(baja_id: int) -> BajaXmlContext:
    baja = Bajas.objects.using(POSTGRES_DB).filter(id_baja=baja_id).first()
    if not baja:
        raise NotFound("Baja no encontrada.")

    recibos_db = list(
        Recibos.objects.using(POSTGRES_DB)
        .filter(baja_id=baja_id)
        .order_by("id_recibo")
    )
    if not recibos_db:
        raise ValidationError("La baja no tiene recibos vinculados.")

    contexts: list[ReciboXmlContext] = []
    motivos: dict[int, str] = {}
    for recibo in recibos_db:
        ctx = fetch_recibo_xml_context(recibo.id_recibo)
        if ctx.id_comprobante not in (
            FACTURA_COMPROBANTE_ID,
            NOTA_CREDITO_COMPROBANTE_ID,
            NOTA_DEBITO_COMPROBANTE_ID,
        ):
            raise ValidationError(
                f"El recibo {recibo.id_recibo} no admite comunicación de baja."
            )
        contexts.append(ctx)
        motivos[recibo.id_recibo] = recibo.motivo_baja or "-"

    emisor = contexts[0]
    return BajaXmlContext(
        id_baja=baja.id_baja,
        ruc_emisor=emisor.ruc_emisor,
        denominacion_emisor=emisor.denominacion_emisor,
        fecha_emision=baja.fecha_emision,
        fecha_comunicacion=baja.fecha_baja,
        lote=baja.lote,
        recibos=contexts,
        motivos_baja=motivos,
    )


def render_baja_xml(ctx: BajaXmlContext) -> str:
    template = _load_template("comunicacion_baja.xml")
    items = []
    for index, recibo_ctx in enumerate(ctx.recibos, start=1):
        items.append(
            _build_baja_item(
                line_id=index,
                ctx=recibo_ctx,
                motivo_baja=ctx.motivos_baja.get(recibo_ctx.id_recibo, "-"),
            )
        )

    mapping = {
        "serie_numero": ctx.serie_numero,
        "fecha_emision": ctx.fecha_emision.strftime("%Y-%m-%d"),
        "fecha_comunicacion": ctx.fecha_comunicacion.strftime("%Y-%m-%d"),
        "ruc_emisor": ctx.ruc_emisor,
        "razon_social_emisor": ctx.denominacion_emisor,
        "items": "".join(items),
    }
    return _replace(template, mapping)


def generar_baja_xml(*, baja_id: int) -> tuple[Path, BajaXmlContext]:
    ctx = fetch_baja_xml_context(baja_id)
    ensure_output_dirs()

    output_path = baja_generar_path(
        ruc=ctx.ruc_emisor,
        fecha_comunicacion=ctx.fecha_comunicacion,
        lote=ctx.lote,
    )
    xml_content = render_baja_xml(ctx)
    output_path.write_text(xml_content, encoding="utf-8")

    Bajas.objects.using(POSTGRES_DB).filter(id_baja=baja_id).update(
        denominacion=ctx.archivo,
    )
    return output_path, ctx
