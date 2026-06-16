from django.db import models
from django.utils import timezone as django_tz
from rest_framework import serializers


class LocalWallDateTimeField(models.DateTimeField):
    """
    Legacy ventas ``timestamp without time zone`` values are naive America/Lima
    wall clock. With USE_TZ=True, Django's DateTimeField would convert through
    UTC on write/read; this field stores and returns the value unchanged.
    """

    def get_prep_value(self, value):
        value = super(models.DateTimeField, self).get_prep_value(value)
        if value is None:
            return None
        value = self.to_python(value)
        if django_tz.is_aware(value):
            value = django_tz.localtime(value).replace(tzinfo=None)
        return value

    def from_db_value(self, value, expression, connection):
        return value


class LocalWallDateTimeSerializerField(serializers.DateTimeField):
    """API representation for LocalWallDateTimeField values (no UTC shift)."""

    def enforce_timezone(self, value):
        if value is None:
            return None
        if django_tz.is_aware(value):
            return value.replace(tzinfo=None)
        return value

    def to_representation(self, value):
        value = self.enforce_timezone(value)
        if value is None:
            return None
        return value.isoformat(sep="T", timespec="microseconds")
