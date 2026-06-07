from rest_framework import serializers

from .legacy_db import next_serial_id
from .models import (
    Catalogos,
    CodigosUnitarios,
    Comprobantes,
    Documentos,
    Ingresos,
    IngresosDetalles,
    Monedas,
    Personas,
    Recibos,
    TiposIgv,
    Usuarios,
)


class CodigosUnitariosSerializer(serializers.ModelSerializer):
    class Meta:
        model = CodigosUnitarios
        fields = [
            "id_codigo_unitario",
            "codigo",
            "descripcion",
        ]


class CatalogosSerializer(serializers.ModelSerializer):
    codigo_unitario = serializers.PrimaryKeyRelatedField(
        queryset=CodigosUnitarios.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Catalogos
        fields = [
            "id_catalogo",
            "codigo",
            "descripcion",
            "valor_unitario",
            "precio_unitario",
            "creado",
            "actualizado",
            "negocio_id",
            "usuario_id",
            "moneda_id",
            "codigo_unitario",
            "tipo_igv_id",
        ]
        read_only_fields = [
            "id_catalogo",
            "creado",
            "actualizado",
            "negocio_id",
            "usuario_id",
        ]

    def create(self, validated_data):
        validated_data["id_catalogo"] = next_serial_id("catalogos", "id_catalogo")
        return super().create(validated_data)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        related = instance.codigo_unitario
        data["codigo_unitario"] = related.descripcion if related else None
        return data


class MonedasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Monedas
        fields = [
            "id_moneda",
            "codigo",
            "descripcion",
            "abreviatura",
            "simbolo",
            "creado",
            "actualizado",
        ]
        read_only_fields = ["id_moneda", "creado", "actualizado"]


class TiposIgvSerializer(serializers.ModelSerializer):
    class Meta:
        model = TiposIgv
        fields = [
            "id_tipo_igv",
            "codigo",
            "descripcion",
            "onerosa",
            "creado",
            "actualizado",
        ]
        read_only_fields = ["id_tipo_igv", "creado", "actualizado"]


class DocumentosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documentos
        fields = [
            "id_documento",
            "descripcion",
            "abreviatura",
        ]
        read_only_fields = ["id_documento",]


class PersonasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Personas
        fields = [
            "id_persona",
            "nombres",
            "apellido_paterno",
            "apellido_materno",
            "razon_social",
            "nombre_comercial",
            "documento",
            "numero_documento",
            "direccion",
            "fecha_nacimiento",
            "nombre_completo",
            "email",
            "creado",
            "actualizado",
        ]
        read_only_fields = ["id_persona", "creado", "actualizado"        ]


class ComprobantesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comprobantes
        fields = [
            "id_comprobante",
            "codigo",
            "descripcion",
            "creado",
            "actualizado",
        ]
        read_only_fields = ["id_comprobante", "creado", "actualizado"]


class RecibosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recibos
        fields = [
            "id_recibo",
            "fecha_emision",
            "fecha_vencimiento",
            "comprobante",
            "serie",
            "numero",
            "exportacion",
            "moneda_id",
            "gravada",
            "inafecta",
            "exonerada",
            "igv",
            "descuento",
            "total",
            "igv_porcentaje",
            "detraccion",
            "observaciones",
            "digest_value",
            "signature_value",
            "enviada_sunat",
            "nombre_comprobante",
            "aceptada_sunat",
            "usuario_id",
            "negocio_id",
            "persona_id",
            "direccion",
            "consulta_ticket",
            "motivo_baja",
            "fecha_baja",
            "fecha_resumen",
            "anulada",
            "resumen_id",
            "tipo_recibo_modificado_id",
            "tipo_nota_credito_id",
            "tipo_nota_debito_id",
            "motivo_modificacion",
            "serie_documento_modificado",
            "numero_documento_modificado",
            "baja_id",
            "observaciones_sunat",
            "codigo_error",
            "error_sunat",
            "gratuita",
        ]
        read_only_fields = ["id_recibo"]


class IngresosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingresos
        fields = [
            "id_ingreso",
            "fecha_emision",
            "numero",
            "moneda_id",
            "total",
            "anulada",
            "usuario_id",
            "negocio_id",
            "persona_id",
            "direccion",
            "motivo_baja",
            "fecha_baja",
            "recibo",
            "serie",
            "comprobante",
            "canjeada",
            "observaciones",
        ]
        read_only_fields = ["id_ingreso"]


class IngresosDetallesSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngresosDetalles
        fields = [
            "id_ingreso_detalle",
            "cantidad",
            "descripcion",
            "total",
            "detalles",
            "ingreso",
            "catalogo_id",
            "creado",
            "actualizado",
            "precio_unitario",
        ]
        read_only_fields = ["id_ingreso_detalle", "creado", "actualizado"]


class UsuariosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuarios
        fields = [
            "id_usuario",
            "usuario",
            "email",
            "telefono",
            "estado",
            "negocio_id",
            "rol_id",
            "persona_id",
        ]
