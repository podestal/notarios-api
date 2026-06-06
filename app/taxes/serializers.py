from rest_framework import serializers

from .models import Catalogos, CodigosUnitarios, Monedas, TiposIgv, Usuarios


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
        read_only_fields = ["id_catalogo", "creado", "actualizado"]

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
