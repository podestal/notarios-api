from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from notaria.pagination import KardexPagination
from .models import Viaje, Participante
from .serializers import ViajeSerializer, ParticipanteSerializer



class ViajeViewSet(viewsets.ModelViewSet):
    queryset = Viaje.objects.all()
    serializer_class = ViajeSerializer
    pagination_class = KardexPagination

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        kardex = request.query_params.get('kardex')
        if kardex:
            queryset = self.queryset.filter(num_kardex=kardex)
        else:
            queryset = self.queryset.all()
        
        # Check if we have results
        if queryset.exists():
            # If only one result, return it as a single object
            if queryset.count() == 1:
                serializer = ViajeSerializer(queryset.first())
            else:
                # If multiple results, use many=True
                serializer = ViajeSerializer(queryset, many=True)
            return Response(serializer.data)
        else:
            # No results found
            return Response({"message": "No viajes found for this kardex"}, status=404)

class ParticipanteViewSet(viewsets.ModelViewSet):
    queryset = Participante.objects.all()
    serializer_class = ParticipanteSerializer
    pagination_class = KardexPagination

