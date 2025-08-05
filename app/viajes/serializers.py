from rest_framework import serializers
from .models import Viaje, Participante

class ParticipanteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participante
        fields = '__all__'

class ViajeSerializer(serializers.ModelSerializer):
    participantes = ParticipanteSerializer(many=True, read_only=True)
    
    class Meta:
        model = Viaje
        fields = '__all__'