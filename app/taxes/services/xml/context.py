from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db import connections
from rest_framework.exceptions import NotFound

from taxes.models import (
    Comprobantes,
    Documentos,
    ItemsRecibos,
    Monedas,
    Personas,
    Recibos,
    TiposIgv,
)
from taxes.services.control_interno import FACTURA_COMPROBANTE_ID
from taxes.services.pdf.numtoletras import numtoletras

from .paths import POSTGRES_DB


@dataclass
class ReciboXmlItem:
    cantidad: int
    descripcion: str
    detalles: str
    precio_unitario: Decimal
    valor_unitario: Decimal
    subtotal: Decimal
    igv: Decimal
    total: Decimal
    codigo_tipo_igv: str
    onerosa: bool


@dataclass
class ReciboXmlContext:
    id_recibo: int
    id_comprobante: int
    codigo_comprobante: str
    comprobante: str
    serie: str
    numero: int
    fecha_emision: datetime
    fecha_vencimiento: datetime
    hora_emision: str
    ruc_emisor: str
    denominacion_emisor: str
    direccion_emisor: str
    codigo_ubigeo: str
    departamento_emisor: str
    provincia_emisor: str
    distrito_emisor: str
    ruc_cliente: str
    tipo_documento: str
    denominacion_cliente: str
    direccion_cliente: str
    moneda_abrev: str
    gravada: Decimal
    igv: Decimal
    total: Decimal
    gratuita: Decimal
    igv_porcentaje: Decimal
    observaciones: str
    codigo_nota_credito: str | None
    tipo_nota_credito: str | None
    codigo_nota_debito: str | None
    tipo_nota_debito: str | None
    codigo_recibo_modificado: str | None
    serie_documento_modificado: str | None
    numero_documento_modificado: str | None
    items: list[ReciboXmlItem]

    @property
    def numero_padded(self) -> str:
        return str(self.numero).zfill(8)

    @property
    def serie_numero(self) -> str:
        return f"{self.serie}-{self.numero_padded}"

    @property
    def nombre_comprobante(self) -> str:
        return (
            f"{self.ruc_emisor}-{self.codigo_comprobante}-"
            f"{self.serie}-{self.numero_padded}"
        )

    @property
    def numero_en_letras(self) -> str:
        return numtoletras(self.total)

    @property
    def ruc_cliente_xml(self) -> str:
        if "SN" in (self.ruc_cliente or "").upper():
            return "-"
        return self.ruc_cliente or "-"

    @property
    def nombre_documento_modificado(self) -> str:
        if not self.serie_documento_modificado or not self.numero_documento_modificado:
            return ""
        numero = str(self.numero_documento_modificado).zfill(8)
        return f"{self.serie_documento_modificado}-{numero}"


def _persona_denominacion(persona: Personas | None, *, comprobante_id: int) -> str:
    if not persona:
        return ""
    if comprobante_id == FACTURA_COMPROBANTE_ID:
        razon_social = (persona.razon_social or "").strip()
        if razon_social and razon_social != "-":
            return razon_social
    return persona.nombre_completo or ""


def _fetch_emisor(negocio_id: int) -> dict:
    with connections[POSTGRES_DB].cursor() as cursor:
        cursor.execute(
            """
            SELECT
                n.ruc,
                n.denominacion,
                n.direccion,
                CASE
                    WHEN dist.codigo ~ '^[0-9]{6}$' THEN dist.codigo
                    ELSE
                        LPAD(COALESCE(dep.codigo, ''), 2, '0')
                        || LPAD(COALESCE(prov.codigo, ''), 2, '0')
                        || LPAD(COALESCE(dist.codigo, ''), 2, '0')
                END AS codigo_ubigeo,
                COALESCE(dep.descripcion, '') AS departamento_emisor,
                COALESCE(prov.descripcion, '') AS provincia_emisor,
                COALESCE(dist.descripcion, '') AS distrito_emisor
            FROM administracion.negocios n
            LEFT JOIN administracion.sedes s ON s.negocio_id = n.id_negocio
            LEFT JOIN ubigeo.distritos dist ON dist.id_distrito = s.distrito_id
            LEFT JOIN ubigeo.provincias prov ON prov.id_provincia = dist.provincia_id
            LEFT JOIN ubigeo.departamentos dep ON dep.id_departamento = prov.departamento_id
            WHERE n.id_negocio = %s
            LIMIT 1
            """,
            [negocio_id],
        )
        row = cursor.fetchone()
        if not row:
            return {}
        columns = [col[0] for col in cursor.description]
        return _apply_sunat_test_overrides(dict(zip(columns, row)))


def _apply_sunat_test_overrides(emisor: dict) -> dict:
    """Override emisor RUC for SUNAT beta when cert/SOL use the demo RUC."""
    test_ruc = os.environ.get("SUNAT_TEST_RUC_EMISOR", "").strip()
    if not test_ruc:
        return emisor
    emisor = dict(emisor)
    emisor["ruc"] = test_ruc
    test_name = os.environ.get("SUNAT_TEST_DENOMINACION_EMISOR", "").strip()
    if test_name:
        emisor["denominacion"] = test_name
    return emisor


def _fetch_nota_credito(tipo_nota_credito_id: int | None) -> tuple[str | None, str | None]:
    if not tipo_nota_credito_id:
        return None, None
    with connections[POSTGRES_DB].cursor() as cursor:
        cursor.execute(
            """
            SELECT codigo, descripcion
            FROM ventas.tipo_nota_credito
            WHERE id_tipo_nota_credito = %s
            LIMIT 1
            """,
            [tipo_nota_credito_id],
        )
        row = cursor.fetchone()
        if not row:
            return None, None
        return row[0], row[1]


def _fetch_nota_debito(tipo_nota_debito_id: int | None) -> tuple[str | None, str | None]:
    if not tipo_nota_debito_id:
        return None, None
    with connections[POSTGRES_DB].cursor() as cursor:
        cursor.execute(
            """
            SELECT codigo, descripcion
            FROM ventas.tipo_nota_debito
            WHERE id_tipo_nota_debito = %s
            LIMIT 1
            """,
            [tipo_nota_debito_id],
        )
        row = cursor.fetchone()
        if not row:
            return None, None
        return row[0], row[1]


def _fetch_comprobante_modificado(tipo_recibo_modificado_id: int | None) -> str | None:
    if not tipo_recibo_modificado_id:
        return None
    comprobante = (
        Comprobantes.objects.using(POSTGRES_DB)
        .filter(id_comprobante=tipo_recibo_modificado_id)
        .values_list("codigo", flat=True)
        .first()
    )
    return comprobante


def fetch_recibo_xml_context(recibo_id: int) -> ReciboXmlContext:
    recibo = Recibos.objects.using(POSTGRES_DB).filter(id_recibo=recibo_id).first()
    if not recibo:
        raise NotFound("Recibo no encontrado.")

    comprobante = Comprobantes.objects.using(POSTGRES_DB).filter(
        id_comprobante=recibo.comprobante_id
    ).first()
    persona = Personas.objects.using(POSTGRES_DB).filter(id_persona=recibo.persona_id).first()
    documento = None
    if persona:
        documento = Documentos.objects.using(POSTGRES_DB).filter(
            id_documento=persona.documento_id
        ).first()
    moneda = Monedas.objects.using(POSTGRES_DB).filter(id_moneda=recibo.moneda_id).first()
    emisor = _fetch_emisor(recibo.negocio_id)

    items_qs = (
        ItemsRecibos.objects.using(POSTGRES_DB)
        .filter(recibo_id=recibo.id_recibo)
        .order_by("id_item")
    )
    tipo_igv_ids = {
        item.tipo_igv_id for item in items_qs if item.tipo_igv_id is not None
    }
    tipos_igv = {
        row.id_tipo_igv: row
        for row in TiposIgv.objects.using(POSTGRES_DB).filter(id_tipo_igv__in=tipo_igv_ids)
    }

    items: list[ReciboXmlItem] = []
    gratuita_total = Decimal("0")
    for item in items_qs:
        tipo_igv = tipos_igv.get(item.tipo_igv_id)
        codigo_tipo_igv = (tipo_igv.codigo if tipo_igv else "10") or "10"
        onerosa = bool(tipo_igv.onerosa) if tipo_igv else True
        if not onerosa:
            gratuita_total += item.subtotal or Decimal("0")
        items.append(
            ReciboXmlItem(
                cantidad=item.cantidad,
                descripcion=item.descripcion or "",
                detalles=item.detalles or "-",
                precio_unitario=item.precio_unitario or Decimal("0"),
                valor_unitario=item.valor_unitario or Decimal("0"),
                subtotal=item.subtotal or Decimal("0"),
                igv=item.igv or Decimal("0"),
                total=item.total or Decimal("0"),
                codigo_tipo_igv=str(codigo_tipo_igv).strip(),
                onerosa=onerosa,
            )
        )

    codigo_nc, tipo_nc = _fetch_nota_credito(recibo.tipo_nota_credito_id)
    codigo_nd, tipo_nd = _fetch_nota_debito(recibo.tipo_nota_debito_id)
    codigo_recibo_modificado = _fetch_comprobante_modificado(recibo.tipo_recibo_modificado_id)

    fecha_emision = recibo.fecha_emision
    hora_emision = fecha_emision.strftime("%H:%M:%S") if fecha_emision else ""

    gratuita = recibo.gratuita if recibo.gratuita is not None else gratuita_total

    return ReciboXmlContext(
        id_recibo=recibo.id_recibo,
        id_comprobante=recibo.comprobante_id,
        codigo_comprobante=comprobante.codigo if comprobante else "",
        comprobante=comprobante.descripcion if comprobante else "",
        serie=recibo.serie,
        numero=recibo.numero,
        fecha_emision=fecha_emision,
        fecha_vencimiento=recibo.fecha_vencimiento,
        hora_emision=hora_emision,
        ruc_emisor=emisor.get("ruc") or "",
        denominacion_emisor=emisor.get("denominacion") or "",
        direccion_emisor=emisor.get("direccion") or "",
        codigo_ubigeo=emisor.get("codigo_ubigeo") or "",
        departamento_emisor=emisor.get("departamento_emisor") or "",
        provincia_emisor=emisor.get("provincia_emisor") or "",
        distrito_emisor=emisor.get("distrito_emisor") or "",
        ruc_cliente=persona.numero_documento if persona else "",
        tipo_documento=documento.codigo if documento else "",
        denominacion_cliente=_persona_denominacion(
            persona, comprobante_id=recibo.comprobante_id
        ),
        direccion_cliente=(recibo.direccion or persona.direccion if persona else "") or "",
        moneda_abrev=moneda.abreviatura if moneda else "PEN",
        gravada=recibo.gravada or Decimal("0"),
        igv=recibo.igv or Decimal("0"),
        total=recibo.total or Decimal("0"),
        gratuita=gratuita or Decimal("0"),
        igv_porcentaje=recibo.igv_porcentaje or Decimal("18"),
        observaciones=recibo.observaciones or "",
        codigo_nota_credito=codigo_nc,
        tipo_nota_credito=tipo_nc,
        codigo_nota_debito=codigo_nd,
        tipo_nota_debito=tipo_nd,
        codigo_recibo_modificado=codigo_recibo_modificado,
        serie_documento_modificado=recibo.serie_documento_modificado,
        numero_documento_modificado=recibo.numero_documento_modificado,
        items=items,
    )
