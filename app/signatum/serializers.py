from rest_framework import serializers

from . import models


class NotarizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Notarization
        fields = "__all__"


class NotarizationReservationSerializer(serializers.ModelSerializer):
    """Full reservation; use for retrieve, list, update."""

    class Meta:
        model = models.NotarizationReservation
        fields = "__all__"
        read_only_fields = (
            "idtipkar",
            "status",
            "held_by",
            "created_at",
        )


class CreateNotarizationReservationSerializer(serializers.ModelSerializer):
    """POST: `kardex` + `idtipkar` (tipo); correlatives are filled server-side per tipo/year."""

    class Meta:
        model = models.NotarizationReservation
        fields = ("kardex", "idtipkar")
