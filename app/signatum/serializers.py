from rest_framework import serializers
from . import models

class NotarizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Notarization
        fields = "__all__"

class NotarizationReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.NotarizationReservation
        fields = "__all__"