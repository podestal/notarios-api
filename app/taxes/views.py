from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from notaria.pagination import KardexPagination

from .models import Catalogos, CodigosUnitarios
from .serializers import CatalogosSerializer, CodigosUnitariosSerializer


class CodigosUnitariosViewSet(ModelViewSet):
    queryset = CodigosUnitarios.objects.all()
    serializer_class = CodigosUnitariosSerializer
    permission_classes = [IsAuthenticated]


class CatalogosViewSet(ModelViewSet):
    serializer_class = CatalogosSerializer
    # permission_classes = [IsAuthenticated]
    pagination_class = KardexPagination

    def get_queryset(self):
        return Catalogos.objects.select_related("codigo_unitario").all()
