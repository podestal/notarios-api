from rest_framework import serializers

from audit.labels import (
    actor_display_for,
    humanize_contratantes_changes,
    humanize_kardex_changes,
    humanize_medio_pago_changes,
    humanize_participa_changes,
    humanize_patrimonial_changes,
    record_label_for,
)
from audit.models import KardexChangeLog
from audit.services import (
    TABLE_CONTRATANTES,
    TABLE_CONTRATANTESXACTO,
    TABLE_DETALLE_MEDIOPAGO,
    TABLE_KARDEX,
    TABLE_PATRIMONIAL,
    drop_hidden_log_fields,
    drop_unchanged_log_fields,
)


class KardexChangeLogSerializer(serializers.ModelSerializer):
    record_label = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()

    def _actor_display(self, instance):
        cache = self.context.setdefault("_kardex_label_cache", {})
        return actor_display_for(
            getattr(instance, "user_id", None),
            username=getattr(instance, "username", "") or "",
            cache=cache,
        )

    def get_user_name(self, instance):
        return self._actor_display(instance).get("user_name") or ""

    def get_first_name(self, instance):
        return self._actor_display(instance).get("first_name") or ""

    def get_last_name(self, instance):
        return self._actor_display(instance).get("last_name") or ""

    def get_record_label(self, instance):
        cache = self.context.setdefault("_kardex_label_cache", {})
        return record_label_for(
            getattr(instance, "table_name", "") or "",
            getattr(instance, "record_pk", "") or "",
            getattr(instance, "changes", None) or {},
            cache=cache,
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        table_name = data.get("table_name") or ""
        cache = self.context.setdefault("_kardex_label_cache", {})
        changes = drop_hidden_log_fields(data.get("changes") or {}, table_name)
        if table_name == TABLE_KARDEX:
            changes = humanize_kardex_changes(changes, cache=cache)
        elif table_name == TABLE_CONTRATANTES:
            changes = humanize_contratantes_changes(changes, cache=cache)
        elif table_name == TABLE_CONTRATANTESXACTO:
            changes = humanize_participa_changes(changes, cache=cache)
        elif table_name == TABLE_PATRIMONIAL:
            changes = humanize_patrimonial_changes(changes, cache=cache)
        elif table_name == TABLE_DETALLE_MEDIOPAGO:
            changes = humanize_medio_pago_changes(changes, cache=cache)
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
            "record_label",
            "action",
            "changes",
            "user_id",
            "username",
            "user_name",
            "first_name",
            "last_name",
            "source",
            "created_at",
        )
        read_only_fields = fields
