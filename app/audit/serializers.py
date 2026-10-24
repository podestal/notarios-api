from rest_framework import serializers

from audit.models import KardexChangeLog


class KardexChangeLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = KardexChangeLog
        fields = (
            "id",
            "kardex",
            "idkardex",
            "table_name",
            "record_pk",
            "action",
            "changes",
            "user_id",
            "username",
            "source",
            "created_at",
        )
        read_only_fields = fields
