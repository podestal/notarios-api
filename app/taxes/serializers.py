from datetime import date, datetime, time

from django.utils import timezone as django_tz
from rest_framework import serializers

from .services.document_lookup import (
    moneda_display,
    persona_documento_display,
    persona_nombres_display,
    usuario_display,
)
from .legacy_db import next_serial_id
from .models import (
    Catalogos,
    CodigosUnitarios,
    Comprobantes,
    Documentos,
    Ingresos,
    IngresosDetalles,
    ItemsRecibos,
    Monedas,
    Personas,
    Recibos,
    Resumenes,
    Series,
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
        read_only_fields = ["id_persona", "creado", "actualizado"]


class PersonaLookupSerializer(serializers.ModelSerializer):
    documento = serializers.IntegerField(source="documento_id", read_only=True)

    class Meta:
        model = Personas
        fields = [
            "id_persona",
            "numero_documento",
            "nombres",
            "apellido_paterno",
            "apellido_materno",
            "nombre_completo",
            "direccion",
            "documento",
        ]


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


class SeriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Series
        fields = [
            "id_serie",
            "serie",
            "sede_id",
            "comprobante",
        ]
        read_only_fields = ["id_serie"]


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


class RecibosReadSerializer(serializers.ModelSerializer):
    comprobante = serializers.IntegerField(source="comprobante_id", read_only=True)
    persona_documento = serializers.SerializerMethodField()
    persona_nombres = serializers.SerializerMethodField()
    usuario = serializers.SerializerMethodField()
    moneda = serializers.SerializerMethodField()

    class Meta:
        model = Recibos
        fields = [
            "id_recibo",
            "fecha_emision",
            "fecha_vencimiento",
            "comprobante",
            "serie",
            "numero",
            "moneda",
            "gravada",
            "inafecta",
            "exonerada",
            "igv",
            "descuento",
            "total",
            "igv_porcentaje",
            "anulada",
            "usuario",
            "negocio_id",
            "persona_documento",
            "persona_nombres",
            "direccion",
            "observaciones",
            "motivo_baja",
            "fecha_baja",
            "enviada_sunat",
            "aceptada_sunat",
            "nombre_comprobante",
        ]

    def get_persona_documento(self, obj):
        persona = self.context.get("personas_by_id", {}).get(obj.persona_id)
        return persona_documento_display(persona)

    def get_persona_nombres(self, obj):
        persona = self.context.get("personas_by_id", {}).get(obj.persona_id)
        return persona_nombres_display(persona, comprobante_id=obj.comprobante_id)

    def get_usuario(self, obj):
        usuario = self.context.get("usuarios_by_id", {}).get(obj.usuario_id)
        personas_by_id = self.context.get("personas_by_id", {})
        return usuario_display(usuario, personas_by_id)

    def get_moneda(self, obj):
        moneda = self.context.get("monedas_by_id", {}).get(obj.moneda_id)
        return moneda_display(moneda)


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
        read_only_fields = [
            "id_ingreso",
            "fecha_emision",
            "numero",
            "usuario_id",
            "negocio_id",
            "comprobante",
        ]


class IngresosReadSerializer(serializers.ModelSerializer):
    comprobante = serializers.IntegerField(source="comprobante_id", read_only=True)
    recibo_id = serializers.IntegerField(read_only=True, allow_null=True)
    persona_documento = serializers.SerializerMethodField()
    persona_nombres = serializers.SerializerMethodField()
    usuario = serializers.SerializerMethodField()
    moneda = serializers.SerializerMethodField()

    class Meta:
        model = Ingresos
        fields = [
            "id_ingreso",
            "fecha_emision",
            "numero",
            "moneda",
            "total",
            "anulada",
            "usuario",
            "negocio_id",
            "persona_documento",
            "persona_nombres",
            "direccion",
            "motivo_baja",
            "fecha_baja",
            "recibo",
            "recibo_id",
            "serie",
            "comprobante",
            "canjeada",
            "observaciones",
        ]

    def get_persona_documento(self, obj):
        persona = self.context.get("personas_by_id", {}).get(obj.persona_id)
        return persona_documento_display(persona)

    def get_persona_nombres(self, obj):
        persona = self.context.get("personas_by_id", {}).get(obj.persona_id)
        return persona_nombres_display(persona)

    def get_usuario(self, obj):
        usuario = self.context.get("usuarios_by_id", {}).get(obj.usuario_id)
        personas_by_id = self.context.get("personas_by_id", {})
        return usuario_display(usuario, personas_by_id)

    def get_moneda(self, obj):
        moneda = self.context.get("monedas_by_id", {}).get(obj.moneda_id)
        return moneda_display(moneda)


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


class FechaEmisionInputField(serializers.Field):
    """
    Accept YYYY-MM-DD or ISO datetime.

    Stored as legacy local Peru wall time with microsecond precision.
    Date-only values use the selected calendar date with the current local time.
    """

    default_error_messages = {
        "invalid": "fecha_emision must be YYYY-MM-DD or an ISO datetime string.",
    }
    _datetime_field = serializers.DateTimeField()

    def to_internal_value(self, data):
        now_local = django_tz.localtime()

        if isinstance(data, datetime):
            parsed = data
        elif isinstance(data, date):
            parsed = datetime.combine(data, now_local.time())
        elif isinstance(data, str):
            value = data.strip()
            if len(value) == 10 and value[4] == "-" and value[7] == "-":
                try:
                    picked_date = date.fromisoformat(value)
                except ValueError:
                    self.fail("invalid")
                parsed = datetime.combine(picked_date, now_local.time())
            else:
                parsed = self._datetime_field.to_internal_value(value)
        else:
            self.fail("invalid")

        if django_tz.is_aware(parsed):
            parsed = django_tz.localtime(parsed).replace(tzinfo=None)

        if parsed.microsecond == 0:
            parsed = parsed.replace(microsecond=now_local.microsecond)

        return parsed


class ControlInternoLineaSerializer(serializers.Serializer):
    catalogo_id = serializers.IntegerField()
    cantidad = serializers.IntegerField()
    descripcion = serializers.CharField(max_length=200)
    detalles = serializers.CharField(max_length=200, required=False, allow_blank=True, default="-")
    precio_unitario = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class CreateControlInternoSerializer(serializers.Serializer):
    fecha_emision = FechaEmisionInputField()
    serie = serializers.CharField(max_length=10)
    moneda_id = serializers.IntegerField()
    persona_id = serializers.IntegerField()
    direccion = serializers.CharField(max_length=200)
    observaciones = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    lineas = ControlInternoLineaSerializer(many=True)

    def validate_lineas(self, value):
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value


class ItemsRecibosSerializer(serializers.ModelSerializer):
    recibo = serializers.IntegerField(source="recibo_id", read_only=True)
    tipo_igv = serializers.IntegerField(source="tipo_igv_id", read_only=True)

    class Meta:
        model = ItemsRecibos
        fields = [
            "id_item",
            "cantidad",
            "descripcion",
            "valor_unitario",
            "precio_unitario",
            "subtotal",
            "igv",
            "total",
            "recibo",
            "catalogo_id",
            "tipo_igv",
            "detalles",
            "creado",
            "actualizado",
        ]
        read_only_fields = ["id_item", "creado", "actualizado"]


class ReciboLineaSerializer(serializers.Serializer):
    catalogo_id = serializers.IntegerField()
    cantidad = serializers.IntegerField()
    descripcion = serializers.CharField(max_length=200)
    detalles = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        default="-",
    )
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class CreateReciboSerializer(serializers.Serializer):
    fecha_emision = FechaEmisionInputField(required=False, allow_null=True)
    serie = serializers.CharField(max_length=10)
    moneda_id = serializers.IntegerField()
    persona_id = serializers.IntegerField()
    direccion = serializers.CharField(max_length=200)
    observaciones = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
    lineas = ReciboLineaSerializer(many=True)
    tipo_nota_credito_id = serializers.IntegerField(required=False, allow_null=True)
    tipo_nota_debito_id = serializers.IntegerField(required=False, allow_null=True)
    tipo_recibo_modificado_id = serializers.IntegerField(required=False, allow_null=True)
    serie_documento_modificado_id = serializers.IntegerField(required=False, allow_null=True)
    numero_documento_modificado = serializers.CharField(
        max_length=60,
        required=False,
        allow_blank=True,
        default="",
    )
    motivo_modificacion = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
    )

    def validate_lineas(self, value):
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value

    def validate(self, attrs):
        from taxes.services.control_interno import (
            NOTA_CREDITO_COMPROBANTE_ID,
            NOTA_DEBITO_COMPROBANTE_ID,
        )
        from taxes.services.recibo import resolve_comprobante_from_serie

        comprobante_id = resolve_comprobante_from_serie(attrs["serie"])
        nota_fields = (
            "tipo_recibo_modificado_id",
            "serie_documento_modificado_id",
            "numero_documento_modificado",
        )

        if comprobante_id == NOTA_CREDITO_COMPROBANTE_ID:
            if attrs.get("tipo_nota_credito_id") is None:
                raise serializers.ValidationError(
                    {"tipo_nota_credito_id": "Requerido para nota de crédito."}
                )
            for field in nota_fields:
                if not attrs.get(field):
                    raise serializers.ValidationError(
                        {field: "Requerido para nota de crédito."}
                    )
        elif comprobante_id == NOTA_DEBITO_COMPROBANTE_ID:
            if attrs.get("tipo_nota_debito_id") is None:
                raise serializers.ValidationError(
                    {"tipo_nota_debito_id": "Requerido para nota de débito."}
                )
            for field in nota_fields:
                if not attrs.get(field):
                    raise serializers.ValidationError(
                        {field: "Requerido para nota de débito."}
                    )

        return attrs


class CreateReciboResponseSerializer(serializers.Serializer):
    recibo = RecibosReadSerializer()
    items = ItemsRecibosSerializer(many=True)


class CanjeIngresoSerializer(serializers.Serializer):
    serie = serializers.CharField(max_length=10)
    observaciones = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
    fecha_emision = FechaEmisionInputField(required=False, allow_null=True)


class CanjeResponseSerializer(serializers.Serializer):
    ingreso = IngresosReadSerializer()
    recibo = RecibosReadSerializer()
    items = ItemsRecibosSerializer(many=True)


class ResumenesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resumenes
        fields = [
            "id_resumen",
            "fecha_resumen",
            "fecha_emision",
            "lote",
            "cantidad",
            "usuario_id",
            "ticket_sunat",
            "denominacion",
            "digest_value",
            "signature_value",
            "enviada_sunat",
            "aceptada_sunat",
        ]
        read_only_fields = ["id_resumen"]


class ResumenesReadSerializer(serializers.ModelSerializer):
    usuario = serializers.SerializerMethodField()

    class Meta:
        model = Resumenes
        fields = [
            "id_resumen",
            "fecha_resumen",
            "fecha_emision",
            "lote",
            "cantidad",
            "usuario",
            "ticket_sunat",
            "denominacion",
            "enviada_sunat",
            "aceptada_sunat",
        ]

    def get_usuario(self, obj):
        usuario = self.context.get("usuarios_by_id", {}).get(obj.usuario_id)
        personas_by_id = self.context.get("personas_by_id", {})
        return usuario_display(usuario, personas_by_id)


class CreateResumenSerializer(serializers.Serializer):
    fecha_comunicacion = serializers.DateField()
    fecha_emision = serializers.DateField()
    comprobante_id = serializers.IntegerField(default=2)
    recibo_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class CreateResumenResponseSerializer(serializers.Serializer):
    resumen = ResumenesReadSerializer()
    recibos = RecibosReadSerializer(many=True)


class AnularIngresoSerializer(serializers.Serializer):
    motivo_baja = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        default="-",
    )


class ControlInternoResponseSerializer(serializers.ModelSerializer):
    comprobante = serializers.IntegerField(source="comprobante_id", read_only=True)
    lineas = serializers.SerializerMethodField()

    class Meta:
        model = Ingresos
        fields = [
            "id_ingreso",
            "fecha_emision",
            "numero",
            "serie",
            "comprobante",
            "moneda_id",
            "persona_id",
            "direccion",
            "observaciones",
            "total",
            "usuario_id",
            "negocio_id",
            "canjeada",
            "anulada",
            "lineas",
        ]

    def get_lineas(self, obj):
        detalles = self.context.get("detalles", [])
        return IngresosDetallesSerializer(detalles, many=True).data


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
