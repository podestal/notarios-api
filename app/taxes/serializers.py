from rest_framework import serializers

from .models import Catalogos, CodigosUnitarios


class CodigosUnitariosSerializer(serializers.ModelSerializer):
    class Meta:
        model = CodigosUnitarios
        fields = [
            "id_codigo_unitario",
            "codigo",
            "descripcion",
        ]


class CatalogosSerializer(serializers.ModelSerializer):
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
