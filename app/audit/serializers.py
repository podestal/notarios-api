from rest_framework import serializers

from audit.labels import humanize_kardex_changes
from audit.models import KardexChangeLog
from audit.services import TABLE_KARDEX, drop_hidden_log_fields, drop_unchanged_log_fields


class KardexChangeLogSerializer(serializers.ModelSerializer):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        table_name = data.get("table_name") or ""
        changes = drop_hidden_log_fields(data.get("changes") or {}, table_name)
        if table_name == TABLE_KARDEX:
            cache = self.context.setdefault("_kardex_label_cache", {})
            changes = humanize_kardex_changes(changes, cache=cache)
        else:
            changes = drop_unchanged_log_fields(changes)
        data["changes"] = changes
        return data

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
