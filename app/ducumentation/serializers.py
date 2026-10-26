from rest_framework import serializers
from . import models




class DocumentosGeneradosSerializer(serializers.ModelSerializer):
    """
    Serializer for the Documentogenerados model.
    This serializer is used to validate and serialize the Documentogenerados data.
    """

    class Meta:
        model = models.Documentogenerados
        fields = '__all__'


class DocumentosLogsSerializer(serializers.ModelSerializer):
    """
    Serializer for the DocumentosLogs model.
    """

    username = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    first_name = serializers.SerializerMethodField()
    last_name = serializers.SerializerMethodField()
    action_label = serializers.SerializerMethodField()

    def _user(self, instance):
        return getattr(instance, "user", None)

    def get_username(self, instance):
        user = self._user(instance)
        return getattr(user, "username", "") or ""

    def get_first_name(self, instance):
        user = self._user(instance)
        return (getattr(user, "first_name", "") or "").strip()

    def get_last_name(self, instance):
        user = self._user(instance)
        return (getattr(user, "last_name", "") or "").strip()

    def get_user_name(self, instance):
        first = self.get_first_name(instance)
        last = self.get_last_name(instance)
        full = f"{first} {last}".strip()
        return full or self.get_username(instance)

    def get_action_label(self, instance):
        return instance.get_action_display() if instance.action else ""

    class Meta:
        model = models.DocumentosLogs
        fields = (
            "id",
            "kardex",
            "user",
            "username",
            "user_name",
            "first_name",
            "last_name",
            "action",
            "action_label",
            "created_at",
        )