from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from rest_framework.exceptions import ValidationError

from taxes.services.control_interno import (
    BOLETA_COMPROBANTE_ID,
    FACTURA_COMPROBANTE_ID,
    NOTA_CREDITO_COMPROBANTE_ID,
    NOTA_DEBITO_COMPROBANTE_ID,
)

from .context import ReciboXmlContext, fetch_recibo_xml_context
from .paths import ensure_output_dirs, generar_path, plantillas_dir

COMPROBANTE_TEMPLATES = {
    FACTURA_COMPROBANTE_ID: "factura.xml",
    BOLETA_COMPROBANTE_ID: "boleta.xml",
    NOTA_CREDITO_COMPROBANTE_ID: "ncredito.xml",
    NOTA_DEBITO_COMPROBANTE_ID: "ndebito.xml",
}

ITEM_TEMPLATES = {
    FACTURA_COMPROBANTE_ID: "factura_item.xml",
    BOLETA_COMPROBANTE_ID: "boleta_item.xml",
    NOTA_CREDITO_COMPROBANTE_ID: "ncredito_item.xml",
    NOTA_DEBITO_COMPROBANTE_ID: "ndebito_item.xml",
}


def _load_template(name: str) -> str:
    path = plantillas_dir() / name
    if not path.is_file():
        raise ValidationError(f"Plantilla XML no encontrada: {path}")
    return path.read_text(encoding="utf-8")


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _replace(template: str, mapping: dict[str, str]) -> str:
    result = template
    for key, value in mapping.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def _item_pricing_rules(*, codigo_tipo_igv: str, ctx: ReciboXmlContext, item) -> dict:
    if codigo_tipo_igv == "36":
        return {
            "codigo_tipo_precio": "02",
            "igv_porcentaje": "0.00",
            "codigo_tipo_tributo": "9996",
            "nombre_tipo_tributo": "GRA",
            "etiqueta_tipo_tributo": "FRE",
            "monto_precio_referente": str(item.valor_unitario),
            "valor_unitario": "0.00",
            "valor_venta_item": str(item.subtotal),
            "monto_total_operacion": str(item.subtotal),
        }
    if codigo_tipo_igv == "15":
        return {
            "codigo_tipo_precio": "02",
            "igv_porcentaje": str(ctx.igv_porcentaje),
            "codigo_tipo_tributo": "9996",
            "nombre_tipo_tributo": "GRA",
            "etiqueta_tipo_tributo": "FRE",
            "monto_precio_referente": str(item.valor_unitario),
            "valor_unitario": "0.00",
            "valor_venta_item": str(item.subtotal),
            "monto_total_operacion": str(item.subtotal),
        }
    if codigo_tipo_igv == "16":
        return {
            "codigo_tipo_precio": "02",
            "igv_porcentaje": str(ctx.igv_porcentaje),
            "codigo_tipo_tributo": "9996",
            "nombre_tipo_tributo": "GRA",
            "etiqueta_tipo_tributo": "FRE",
            "monto_precio_referente": str(item.valor_unitario),
            "valor_unitario": "0.00",
            "valor_venta_item": str(item.subtotal),
            "monto_total_operacion": str(item.subtotal),
        }
    return {
        "codigo_tipo_precio": "01",
        "igv_porcentaje": str(ctx.igv_porcentaje),
        "codigo_tipo_tributo": "1000",
        "nombre_tipo_tributo": "IGV",
        "etiqueta_tipo_tributo": "VAT",
        "monto_precio_referente": str(item.precio_unitario),
        "valor_unitario": str(item.valor_unitario),
        "valor_venta_item": str(item.subtotal),
        "monto_total_operacion": str(item.subtotal),
    }


def _build_gravadas(ctx: ReciboXmlContext) -> str:
    if ctx.gravada <= 0:
        return ""
    template = _load_template("gravada.xml")
    return _replace(
        template,
        {
            "moneda_abrev_gravada": ctx.moneda_abrev,
            "impuesto_total_igv": str(ctx.igv),
            "monto_total_gravadas": str(ctx.gravada),
            "codigo_tipo_tributo_gravada": "1000",
            "nombre_tipo_tributo_gravada": "IGV",
            "etiqueta_tipo_tributo_gravada": "VAT",
        },
    )


def _build_gratuitas(ctx: ReciboXmlContext) -> str:
    if ctx.gratuita <= 0:
        return ""

    suma_igv_gratuita = Decimal("0")
    for item in ctx.items:
        if item.codigo_tipo_igv in {"15", "16"}:
            total_line = item.total
            suma_igv_gratuita += total_line - (total_line / Decimal("1.18"))

    template = _load_template("gratuita.xml")
    return _replace(
        template,
        {
            "moneda_abrev_gratuita": ctx.moneda_abrev,
            "monto_total_gratuita": str(ctx.gratuita),
            "impuesto_total_igv_gratuita": f"{suma_igv_gratuita:.2f}",
            "codigo_tipo_tributo_gratuita": "9996",
            "nombre_tipo_tributo_gratuita": "GRA",
            "etiqueta_tipo_tributo_gratuita": "FRE",
        },
    )


def _build_items(ctx: ReciboXmlContext) -> str:
    item_template_name = ITEM_TEMPLATES.get(ctx.id_comprobante)
    if not item_template_name:
        raise ValidationError(
            f"Tipo de comprobante {ctx.id_comprobante} no soportado para XML."
        )
    item_template = _load_template(item_template_name)
    rendered = []
    for index, item in enumerate(ctx.items, start=1):
        pricing = _item_pricing_rules(codigo_tipo_igv=item.codigo_tipo_igv, ctx=ctx, item=item)
        monto_total_operacion = f"{Decimal(pricing['monto_total_operacion']):.2f}".replace(",", "")
        valor_unitario = _format_decimal(Decimal(pricing["valor_unitario"]))
        rendered.append(
            _replace(
                item_template,
                {
                    "item_id": str(index),
                    "cantidad": str(item.cantidad),
                    "descripcion": item.descripcion,
                    "detalles": item.detalles,
                    "precio": _format_decimal(Decimal(pricing["monto_precio_referente"])),
                    "codigo_tipo_precio": pricing["codigo_tipo_precio"],
                    "codigos_tipos_igv": item.codigo_tipo_igv,
                    "codigo_tipo_tributo": pricing["codigo_tipo_tributo"],
                    "nombre_tipo_tributo": pricing["nombre_tipo_tributo"],
                    "etiqueta_tipo_tributo": pricing["etiqueta_tipo_tributo"],
                    "valor_venta_item": pricing["valor_venta_item"],
                    "monto_total_operacion": monto_total_operacion,
                    "total": str(item.total),
                    "igv": str(item.igv),
                    "igv_porcentaje": pricing["igv_porcentaje"],
                    "valor_unitario": valor_unitario,
                    "moneda_abreviatura": ctx.moneda_abrev,
                },
            )
        )
    return "".join(rendered)


def _base_mapping(ctx: ReciboXmlContext) -> dict[str, str]:
    fecha_emision = ctx.fecha_emision.strftime("%Y-%m-%d")
    fecha_vencimiento = (
        ctx.fecha_vencimiento.strftime("%Y-%m-%d")
        if hasattr(ctx.fecha_vencimiento, "strftime")
        else str(ctx.fecha_vencimiento)
    )
    return {
        "codigo_comprobante": ctx.codigo_comprobante,
        "serie_numero": ctx.serie_numero,
        "ruc_emisor": ctx.ruc_emisor,
        "codigo_ubigeo_emisor": ctx.codigo_ubigeo,
        "fecha_emision": fecha_emision,
        "hora_emision": ctx.hora_emision,
        "fecha_vencimiento": fecha_vencimiento,
        "numero_en_letras": ctx.numero_en_letras,
        "moneda_abrev": ctx.moneda_abrev,
        "razon_social_emisor": ctx.denominacion_emisor,
        "tipo_documento": ctx.tipo_documento,
        "ruc_cliente": ctx.ruc_cliente_xml,
        "nombre_cliente": ctx.denominacion_cliente,
        "departamento_emisor": ctx.departamento_emisor,
        "provincia_emisor": ctx.provincia_emisor,
        "distrito_emisor": ctx.distrito_emisor,
        "direccion_emisor": ctx.direccion_emisor,
        "monto_total": str(ctx.total),
        "impuesto_total": str(ctx.igv),
        "total_gravadas": str(ctx.gravada),
        "gravadas": _build_gravadas(ctx),
        "gratuitas": _build_gratuitas(ctx),
        "items": _build_items(ctx),
    }


def render_recibo_xml(ctx: ReciboXmlContext) -> str:
    template_name = COMPROBANTE_TEMPLATES.get(ctx.id_comprobante)
    if not template_name:
        raise ValidationError(
            f"Tipo de comprobante {ctx.id_comprobante} no soportado para XML."
        )
    template = _load_template(template_name)
    mapping = _base_mapping(ctx)

    if ctx.id_comprobante == NOTA_CREDITO_COMPROBANTE_ID:
        mapping.update(
            {
                "codigo_nota_credito": ctx.codigo_nota_credito or "",
                "tipo_nota_credito": ctx.tipo_nota_credito or "",
                "codigo_recibo_modificado": ctx.codigo_recibo_modificado or "",
                "nombre_documento_modificado": ctx.nombre_documento_modificado,
            }
        )
    if ctx.id_comprobante == NOTA_DEBITO_COMPROBANTE_ID:
        mapping.update(
            {
                "codigo_nota_debito": ctx.codigo_nota_debito or "",
                "tipo_nota_debito": ctx.tipo_nota_debito or "",
                # Legacy ndebito.xml reuses the nota-credito placeholder names.
                "codigo_nota_credito": ctx.codigo_nota_debito or "",
                "tipo_nota_credito": ctx.tipo_nota_debito or "",
                "codigo_recibo_modificado": ctx.codigo_recibo_modificado or "",
                "nombre_documento_modificado": ctx.nombre_documento_modificado,
            }
        )

    # Keep legacy-style output: plain string substitution, CDATA and formatting preserved.
    return _replace(template, mapping)


def generar_recibo_xml(*, recibo_id: int, ctx: ReciboXmlContext | None = None) -> Path:
    context = ctx or fetch_recibo_xml_context(recibo_id)
    ensure_output_dirs()
    output_path = generar_path(
        ruc=context.ruc_emisor,
        codigo_comprobante=context.codigo_comprobante,
        serie=context.serie,
        numero=context.numero,
    )
    xml_content = render_recibo_xml(context)
    output_path.write_text(xml_content, encoding="utf-8")
    return output_path
