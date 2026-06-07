from rest_framework import serializers

from .legacy_db import next_serial_id
from .models import (
    Catalogos,
    CodigosUnitarios,
    Documentos,
    Monedas,
    Personas,
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
            # "codigo",
            "descripcion",
            "abreviatura",
            # "creado",
            # "actualizado",
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
        read_only_fields = ["id_persona", "creado", "actualizado"]


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
