from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
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
    Series,
    TiposIgv,
    Usuarios,
)
from .serializers import (
    CatalogosSerializer,
    CodigosUnitariosSerializer,
    ComprobantesSerializer,
    ControlInternoResponseSerializer,
    CreateControlInternoSerializer,
    DocumentosSerializer,
    IngresosDetallesSerializer,
    IngresosReadSerializer,
    IngresosSerializer,
    MonedasSerializer,
    PersonasSerializer,
    RecibosSerializer,
    SeriesSerializer,
    TiposIgvSerializer,
    UsuariosSerializer,
)
from .services.control_interno import (
    CONTROL_INTERNO_COMPROBANTE_ID,
    create_control_interno,
)
from .ingresos_context import ingresos_lookup_context

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
    permission_classes = [IsAuthenticated]


class SeriesViewSet(ModelViewSet):
    queryset = Series.objects.all().order_by("serie")
    serializer_class = SeriesSerializer
    # permission_classes = [IsAuthenticated]
    lookup_field = "id_serie"

    @action(detail=False, methods=["get"], url_path="control_interno")
    def control_interno(self, request):
        queryset = self.queryset.filter(comprobante_id=CONTROL_INTERNO_COMPROBANTE_ID)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class RecibosViewSet(ModelViewSet):
    queryset = Recibos.objects.all()
    serializer_class = RecibosSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]


class IngresosViewSet(ModelViewSet):
    serializer_class = IngresosSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Ingresos.objects.all().order_by("-fecha_emision", "-id_ingreso")

        user = self.request.user
        if user.negocio_id is not None:
            qs = qs.filter(negocio_id=user.negocio_id)

        params = self.request.query_params

        fecha_desde = params.get("fecha_emision_desde", "").strip()
        if fecha_desde:
            date_value = parse_date(fecha_desde)
            if date_value:
                qs = qs.filter(fecha_emision__date__gte=date_value)
            else:
                parsed = parse_datetime(fecha_desde)
                if parsed:
                    qs = qs.filter(fecha_emision__gte=parsed)

        fecha_hasta = params.get("fecha_emision_hasta", "").strip()
        if fecha_hasta:
            date_value = parse_date(fecha_hasta)
            if date_value:
                qs = qs.filter(fecha_emision__date__lte=date_value)
            else:
                parsed = parse_datetime(fecha_hasta)
                if parsed:
                    qs = qs.filter(fecha_emision__lte=parsed)

        persona_documento = params.get("persona_documento", "").strip()
        if persona_documento:
            persona_ids = Personas.objects.filter(
                numero_documento__icontains=persona_documento,
            ).values_list("id_persona", flat=True)
            qs = qs.filter(persona_id__in=persona_ids)

        persona_nombres = params.get("persona_nombres", "").strip()
        if persona_nombres:
            persona_ids = Personas.objects.filter(
                Q(nombre_completo__icontains=persona_nombres)
                | Q(nombres__icontains=persona_nombres)
                | Q(apellido_paterno__icontains=persona_nombres)
                | Q(apellido_materno__icontains=persona_nombres)
            ).values_list("id_persona", flat=True)
            qs = qs.filter(persona_id__in=persona_ids)

        usuario = params.get("usuario", "").strip()
        if usuario:
            persona_ids = Personas.objects.filter(
                Q(nombre_completo__icontains=usuario)
                | Q(nombres__icontains=usuario)
                | Q(apellido_paterno__icontains=usuario)
                | Q(apellido_materno__icontains=usuario)
            ).values_list("id_persona", flat=True)
            usuario_ids = Usuarios.objects.filter(
                Q(usuario__icontains=usuario) | Q(persona_id__in=persona_ids)
            ).values_list("id_usuario", flat=True)
            qs = qs.filter(usuario_id__in=usuario_ids)

        return qs

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return IngresosReadSerializer
        return IngresosSerializer

    def _read_serializer(self, ingresos, *, many: bool):
        items = ingresos if many else [ingresos]
        context = {
            **self.get_serializer_context(),
            **ingresos_lookup_context(items),
        }
        return IngresosReadSerializer(ingresos, many=many, context=context)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self._read_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self._read_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self._read_serializer(instance, many=False)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        raise ValidationError(
            "Use POST /taxes/ingresos/control-interno/ to create ingresos."
        )

    @action(detail=False, methods=["post"], url_path="control-interno")
    def control_interno(self, request):
        user = request.user
        if user.taxes_usuario_id is None or user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (taxes_usuario_id / negocio_id)."
            )

        serializer = CreateControlInternoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ingreso, detalles = create_control_interno(
            serializer.validated_data,
            usuario_id=user.taxes_usuario_id,
            negocio_id=user.negocio_id,
        )

        response = ControlInternoResponseSerializer(
            ingreso,
            context={"detalles": detalles},
        )
        return Response(response.data, status=status.HTTP_201_CREATED)


class IngresosDetallesViewSet(ModelViewSet):
    queryset = IngresosDetalles.objects.all()
    serializer_class = IngresosDetallesSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]


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
