from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from core.permissions import IsSuperuser
from notaria.pagination import KardexPagination

from .models import (
    Catalogos,
    CodigosUnitarios,
    Comprobantes,
    Documentos,
    Ingresos,
    IngresosDetalles,
    Monedas,
    Personas,
    Recibos,
    TiposIgv,
    Usuarios,
)
from .serializers import (
    CatalogosSerializer,
    CodigosUnitariosSerializer,
    ComprobantesSerializer,
    DocumentosSerializer,
    IngresosDetallesSerializer,
    IngresosSerializer,
    MonedasSerializer,
    PersonasSerializer,
    RecibosSerializer,
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

        user = self.request.user
        if user.negocio_id is not None:
            qs = qs.filter(negocio_id=user.negocio_id)

        codigo = self.request.query_params.get("codigo", "").strip()
        if codigo:
            qs = qs.filter(codigo__icontains=codigo)

        descripcion = self.request.query_params.get("descripcion", "").strip()
        if descripcion:
            qs = qs.filter(descripcion__icontains=descripcion)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user.taxes_usuario_id is None or user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (taxes_usuario_id / negocio_id)."
            )
        serializer.save(
            usuario_id=user.taxes_usuario_id,
            negocio_id=user.negocio_id,
        )


class MonedasViewSet(ModelViewSet):
    queryset = Monedas.objects.all()
    serializer_class = MonedasSerializer
    permission_classes = [IsAuthenticated]


class TiposIgvViewSet(ModelViewSet):
    queryset = TiposIgv.objects.all()
    serializer_class = TiposIgvSerializer
    permission_classes = [IsAuthenticated]


class DocumentosViewSet(ModelViewSet):
    queryset = Documentos.objects.all()
    serializer_class = DocumentosSerializer
    permission_classes = [IsAuthenticated]


class PersonasViewSet(ModelViewSet):
    serializer_class = PersonasSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Personas.objects.all()

        nombres = self.request.query_params.get("nombres", "").strip()
        if nombres:
            qs = qs.filter(nombres__icontains=nombres)

        apellido_paterno = self.request.query_params.get("apellido_paterno", "").strip()
        if apellido_paterno:
            qs = qs.filter(apellido_paterno__icontains=apellido_paterno)

        apellido_materno = self.request.query_params.get("apellido_materno", "").strip()
        if apellido_materno:
            qs = qs.filter(apellido_materno__icontains=apellido_materno)

        razon_social = self.request.query_params.get("razon_social", "").strip()
        if razon_social:
            qs = qs.filter(razon_social__icontains=razon_social)

        numero_documento = self.request.query_params.get("numero_documento", "").strip()
        if numero_documento:
            qs = qs.filter(numero_documento__icontains=numero_documento)

        documento = self.request.query_params.get("documento", "").strip()
        if documento:
            qs = qs.filter(documento_id=documento)

        return qs


class ComprobantesViewSet(ModelViewSet):
    queryset = Comprobantes.objects.all()
    serializer_class = ComprobantesSerializer
    # permission_classes = [IsAuthenticated]


class RecibosViewSet(ModelViewSet):
    queryset = Recibos.objects.all()
    serializer_class = RecibosSerializer
    pagination_class = KardexPagination
    # permission_classes = [IsAuthenticated]


class IngresosViewSet(ModelViewSet):
    queryset = Ingresos.objects.all()
    serializer_class = IngresosSerializer
    pagination_class = KardexPagination
    # permission_classes = [IsAuthenticated]


class IngresosDetallesViewSet(ModelViewSet):
    queryset = IngresosDetalles.objects.all()
    serializer_class = IngresosDetallesSerializer
    pagination_class = KardexPagination
    # permission_classes = [IsAuthenticated]


class UsuariosViewSet(ReadOnlyModelViewSet):
    serializer_class = UsuariosSerializer
    permission_classes = [IsAuthenticated, IsSuperuser]
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
