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
    permission_classes = [IsAuthenticated]
    pagination_class = KardexPagination

    def get_queryset(self):
        qs = Catalogos.objects.select_related("codigo_unitario").all()

        codigo = self.request.query_params.get("codigo", "").strip()
        if codigo:
            qs = qs.filter(codigo__icontains=codigo)

        descripcion = self.request.query_params.get("descripcion", "").strip()
        if descripcion:
            qs = qs.filter(descripcion__icontains=descripcion)

        return qs
