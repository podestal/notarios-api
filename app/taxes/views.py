from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from core.permissions import IsSuperuser
from notaria.pagination import KardexPagination

from .models import Catalogos, CodigosUnitarios, Monedas, TiposIgv, Usuarios
from .serializers import (
    CatalogosSerializer,
    CodigosUnitariosSerializer,
    MonedasSerializer,
    TiposIgvSerializer,
    UsuariosSerializer,
)

User = get_user_model()


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


class MonedasViewSet(ModelViewSet):
    queryset = Monedas.objects.all()
    serializer_class = MonedasSerializer
    permission_classes = [IsAuthenticated]


class TiposIgvViewSet(ModelViewSet):
    queryset = TiposIgv.objects.all()
    serializer_class = TiposIgvSerializer
    permission_classes = [IsAuthenticated]


class UsuariosViewSet(ReadOnlyModelViewSet):
    serializer_class = UsuariosSerializer
    # permission_classes = [IsAuthenticated, IsSuperuser]
    # pagination_class = KardexPagination
    lookup_field = "id_usuario"

    def get_queryset(self):
        # Materialize on MariaDB — lazy QuerySet would become a Postgres subquery.
        mapped_ids = list(
            User.objects.using("default")
            .filter(taxes_usuario_id__isnull=False)
            .values_list("taxes_usuario_id", flat=True)
        )

        qs = Usuarios.objects.exclude(id_usuario__in=mapped_ids).order_by("usuario")

        usuario = self.request.query_params.get("usuario", "").strip()
        if usuario:
            qs = qs.filter(usuario__icontains=usuario)

        email = self.request.query_params.get("email", "").strip()
        if email:
            qs = qs.filter(email__icontains=email)

        return qs
