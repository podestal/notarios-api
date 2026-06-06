from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from .models import Catalogos, CodigosUnitarios
from .serializers import CatalogosSerializer, CodigosUnitariosSerializer


class CodigosUnitariosViewSet(ModelViewSet):
    queryset = CodigosUnitarios.objects.all()
    serializer_class = CodigosUnitariosSerializer
    permission_classes = [IsAuthenticated]


class CatalogosViewSet(ModelViewSet):
    queryset = Catalogos.objects.all()
    serializer_class = CatalogosSerializer
    permission_classes = [IsAuthenticated]
