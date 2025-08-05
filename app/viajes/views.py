from rest_framework import viewsets

from notaria.pagination import KardexPagination
from .models import Viaje, Participante
from .serializers import ViajeSerializer, ParticipanteSerializer


class ViajeViewSet(viewsets.ModelViewSet):
    queryset = Viaje.objects.all()
    serializer_class = ViajeSerializer
    pagination_class = KardexPagination

class ParticipanteViewSet(viewsets.ModelViewSet):
    queryset = Participante.objects.all()
    serializer_class = ParticipanteSerializer
    pagination_class = KardexPagination
