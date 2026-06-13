from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from rest_framework.exceptions import NotFound, ValidationError

from taxes.models import Recibos, Resumenes
from taxes.services.control_interno import (
    BOLETA_COMPROBANTE_ID,
    NOTA_CREDITO_COMPROBANTE_ID,
)

from .context import ReciboXmlContext, fetch_recibo_xml_context
from .generar import _load_template, _replace
from .paths import (
    POSTGRES_DB,
    ensure_output_dirs,
    firmar_path,
    resumen_archivo_name,
    resumen_generar_path,
    resumen_serie_numero,
)


@dataclass
class ResumenXmlContext:
    id_resumen: int
    ruc_emisor: str
    denominacion_emisor: str
    fecha_emision: date
    fecha_comunicacion: date
    lote: int
    recibos: list[ReciboXmlContext]

    @property
    def serie_numero(self) -> str:
        return resumen_serie_numero(
            fecha_comunicacion=self.fecha_comunicacion,
            lote=self.lote,
        )

    @property
    def archivo(self) -> str:
        return resumen_archivo_name(
            ruc=self.ruc_emisor,
            fecha_comunicacion=self.fecha_comunicacion,
            lote=self.lote,
        )


def _amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _build_resumen_gravadas(ctx: ReciboXmlContext) -> str:
    if ctx.gravada <= 0:
        return ""
    template = _load_template("resumen_gravada.xml")
    return _replace(
        template,
        {
            "moneda_abrev_gravada": ctx.moneda_abrev,
            "subtotal_gravada": _amount(ctx.gravada),
            "tipo_importe_total": "01",
        },
    )


def _build_resumen_gratuitas(ctx: ReciboXmlContext) -> str:
    if ctx.gratuita <= 0:
        return ""
    template = _load_template("resumen_gratuita.xml")
    return _replace(
        template,
        {
            "moneda_abrev_gratuita": ctx.moneda_abrev,
            "subtotal_gratuita": _amount(ctx.gratuita),
            "tipo_importe_total": "05",
        },
    )


def _condicion_comprobante(*, anulada: bool) -> str:
    return "3" if anulada else "1"


def _build_resumen_item(
    *,
    line_id: int,
    ctx: ReciboXmlContext,
    anulada: bool,
) -> str:
    if ctx.codigo_comprobante == "07":
        template_name = "resumen_item_ncredito.xml"
    else:
        template_name = "resumen_item.xml"

    template = _load_template(template_name)
    mapping = {
        "item_id": str(line_id),
        "codigo_comprobante": ctx.codigo_comprobante,
        "serie": ctx.serie,
        "numero": ctx.numero_padded,
        "numero_documento_cliente": ctx.ruc_cliente or "-",
        "tipo_documento_cliente": ctx.tipo_documento or "1",
        "condicion_comprobante": _condicion_comprobante(anulada=anulada),
        "moneda_abreviatura": ctx.moneda_abrev,
        "total": _amount(ctx.total),
        "impuesto_total": _amount(ctx.igv),
        "gravadas": _build_resumen_gravadas(ctx),
        "gratuitas": _build_resumen_gratuitas(ctx),
    }
    if template_name == "resumen_item_ncredito.xml":
        mapping.update(
            {
                "codigo_recibo_modificado": ctx.codigo_recibo_modificado or "",
                "nombre_documento_modificado": ctx.nombre_documento_modificado,
            }
        )
    return _replace(template, mapping)


def fetch_resumen_xml_context(resumen_id: int) -> ResumenXmlContext:
    resumen = Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).first()
    if not resumen:
        raise NotFound("Resumen no encontrado.")

    recibos = list(
        Recibos.objects.using(POSTGRES_DB)
        .filter(resumen_id=resumen_id)
        .order_by("id_recibo")
    )
    if not recibos:
        raise ValidationError("El resumen no tiene recibos vinculados.")

    contexts: list[ReciboXmlContext] = []
    for recibo in recibos:
        ctx = fetch_recibo_xml_context(recibo.id_recibo)
        if ctx.id_comprobante not in (BOLETA_COMPROBANTE_ID, NOTA_CREDITO_COMPROBANTE_ID):
            raise ValidationError(
                f"El recibo {recibo.id_recibo} no es boleta ni nota de crédito."
            )
        signed_path = firmar_path(
            ruc=ctx.ruc_emisor,
            codigo_comprobante=ctx.codigo_comprobante,
            serie=ctx.serie,
            numero=ctx.numero,
        )
        if not signed_path.is_file():
            raise ValidationError(
                f"El recibo {recibo.id_recibo} no tiene XML firmado. "
                "Genérelo antes de enviar el resumen."
            )
        contexts.append(ctx)

    emisor = contexts[0]
    return ResumenXmlContext(
        id_resumen=resumen.id_resumen,
        ruc_emisor=emisor.ruc_emisor,
        denominacion_emisor=emisor.denominacion_emisor,
        fecha_emision=resumen.fecha_emision,
        fecha_comunicacion=resumen.fecha_resumen,
        lote=resumen.lote,
        recibos=contexts,
    )


def render_resumen_xml(ctx: ResumenXmlContext, *, recibos_anulados: dict[int, bool]) -> str:
    template = _load_template("resumen.xml")
    items = []
    for index, recibo_ctx in enumerate(ctx.recibos, start=1):
        anulada = recibos_anulados.get(recibo_ctx.id_recibo, False)
        items.append(
            _build_resumen_item(
                line_id=index,
                ctx=recibo_ctx,
                anulada=anulada,
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


def generar_resumen_xml(*, resumen_id: int) -> tuple[Path, ResumenXmlContext]:
    resumen = Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).first()
    if not resumen:
        raise NotFound("Resumen no encontrado.")

    recibos = {
        row.id_recibo: bool(row.anulada)
        for row in Recibos.objects.using(POSTGRES_DB).filter(resumen_id=resumen_id)
    }
    ctx = fetch_resumen_xml_context(resumen_id)
    ensure_output_dirs()

    output_path = resumen_generar_path(
        ruc=ctx.ruc_emisor,
        fecha_comunicacion=ctx.fecha_comunicacion,
        lote=ctx.lote,
    )
    xml_content = render_resumen_xml(ctx, recibos_anulados=recibos)
    output_path.write_text(xml_content, encoding="utf-8")

    Resumenes.objects.using(POSTGRES_DB).filter(id_resumen=resumen_id).update(
        denominacion=ctx.archivo,
    )
    return output_path, ctx
