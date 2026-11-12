from rest_framework import serializers

from documentos.models import DocumentoBien


class DocumentoBienSerializer(serializers.ModelSerializer):
    linked = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoBien
        fields = (
            "id",
            "tipo",
            "status",
            "original_filename",
            "stored_filename",
            "relative_path",
            "file_size",
            "placa",
            "partida",
            "oficina",
            "parsed",
            "parse_error",
            "detveh",
            "kardex",
            "idtipacto",
            "applied_at",
            "linked",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_linked(self, obj: DocumentoBien) -> bool:
        return obj.detveh is not None


class DocumentoVehicularUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="SUNARP Boleta Informativa PDF")


class DocumentoVehicularApplySerializer(serializers.Serializer):
    documento_id = serializers.IntegerField(min_value=1)
    kardex = serializers.CharField(max_length=30)
    idtipacto = serializers.CharField(max_length=20)
    replace_existing = serializers.BooleanField(required=False, default=True)
    overwrite_detalle = serializers.BooleanField(required=False, default=True)
    detveh = serializers.IntegerField(required=False, allow_null=True, min_value=1)
