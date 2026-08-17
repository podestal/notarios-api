from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from core.permissions import IsSuperuser
from notaria.pagination import KardexPagination

import logging

logger = logging.getLogger(__name__)

from .models import (
    Bajas,
    Catalogos,
    CodigosUnitarios,
    Comprobantes,
    Documentos,
    Ingresos,
    IngresosDetalles,
    ItemsRecibos,
    Monedas,
    Personas,
    Recibos,
    Resumenes,
    Series,
    SunatOutbox,
    TipoNotaCredito,
    TipoNotaDebito,
    TiposIgv,
    Usuarios,
)
from .serializers import (
    AnularIngresoSerializer,
    BajasReadSerializer,
    BajasSerializer,
    CanjeIngresoSerializer,
    CanjeResponseSerializer,
    CatalogosSerializer,
    CodigosUnitariosSerializer,
    ComprobantesSerializer,
    ControlInternoResponseSerializer,
    CreateControlInternoSerializer,
    CreateReciboResponseSerializer,
    CreateReciboSerializer,
    ConsultarTicketBajaSerializer,
    ConsultarTicketResumenSerializer,
    CreateBajaResponseSerializer,
    CreateBajaSerializer,
    CreateResumenResponseSerializer,
    CreateResumenSerializer,
    EnviarBoletaResumenSerializer,
    DocumentosSerializer,
    IngresosDetallesSerializer,
    IngresosReadSerializer,
    IngresosSerializer,
    ItemsRecibosSerializer,
    MonedasSerializer,
    PersonaLookupSerializer,
    PersonasSerializer,
    RecibosReadSerializer,
    RecibosSerializer,
    ResumenesReadSerializer,
    ResumenesSerializer,
    SeriesSerializer,
    TipoNotaCreditoSerializer,
    TipoNotaDebitoSerializer,
    TiposIgvSerializer,
    UsuariosSerializer,
    CreateTaxesUsuarioSerializer,
    CreateTaxesUsuarioResponseSerializer,
)
from .services.usuario import create_taxes_usuario
from .services.canje import canjear_ingreso
from .services.control_interno import (
    BOLETA_COMPROBANTE_ID,
    CONTROL_INTERNO_COMPROBANTE_ID,
    FACTURA_COMPROBANTE_ID,
    NOTA_CREDITO_COMPROBANTE_ID,
    NOTA_DEBITO_COMPROBANTE_ID,
    create_control_interno,
)
from .services.recibo import boletas_pendientes_sunat_queryset, create_recibo
from .services.baja import (
    anular_boleta_recibo,
    create_baja,
    recibos_anulados_queryset,
    recibos_pendientes_baja_queryset,
)
from .services.resumen import (
    create_resumen,
    create_resumen_for_single_recibo,
    recibos_pendientes_queryset,
)
from .legacy_db import POSTGRES_DB
from .services.document_lookup import document_lookup_context
from .services.document_queryset import apply_document_list_filters
from .services.document_views import DocumentReadViewSetMixin
from .services.kardex_billing import (
    lock_kardex_for_billing,
    mark_kardex_as_billed,
    normalize_kardex,
)
from .services.pdf import generate_ingreso_pdf, generate_recibo_pdf
from .services.sunat_errors import (
    build_sunat_user_payload,
    recibo_needs_sunat_retry,
    resumen_needs_sunat_retry,
)
from .services.sunat_outbox import (
    enqueue_recibo_send,
    enqueue_resumen_send,
    get_active_outbox,
)
from .services.xml import (
    consultar_ticket_baja,
    consultar_ticket_resumen,
    enviar_recibo_sunat,
    procesar_baja_sunat,
    procesar_resumen_sunat,
)

User = get_user_model()

PERSONA_LOOKUP_MAX_RESULTS = 50
PERSONA_LOOKUP_MIN_LENGTH = 2


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


class TipoNotaCreditoViewSet(ReadOnlyModelViewSet):
    """SUNAT credit-note reason catalog (ventas.tipo_nota_credito)."""

    serializer_class = TipoNotaCreditoSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id_tipo_nota_credito"

    def get_queryset(self):
        qs = TipoNotaCredito.objects.all().order_by("id_tipo_nota_credito")
        codigo = self.request.query_params.get("codigo", "").strip()
        if codigo:
            qs = qs.filter(codigo__icontains=codigo)
        descripcion = self.request.query_params.get("descripcion", "").strip()
        if descripcion:
            qs = qs.filter(descripcion__icontains=descripcion)
        return qs


class TipoNotaDebitoViewSet(ReadOnlyModelViewSet):
    """SUNAT debit-note reason catalog (ventas.tipo_nota_debito)."""

    serializer_class = TipoNotaDebitoSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id_tipo_nota_debito"

    def get_queryset(self):
        qs = TipoNotaDebito.objects.all().order_by("id_tipo_nota_debito")
        codigo = self.request.query_params.get("codigo", "").strip()
        if codigo:
            qs = qs.filter(codigo__icontains=codigo)
        descripcion = self.request.query_params.get("descripcion", "").strip()
        if descripcion:
            qs = qs.filter(descripcion__icontains=descripcion)
        return qs


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

    @action(detail=False, methods=["get"], url_path="lookup")
    def lookup(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            raise ValidationError("Query param 'q' is required.")
        if len(q) < PERSONA_LOOKUP_MIN_LENGTH:
            raise ValidationError(
                f"q must be at least {PERSONA_LOOKUP_MIN_LENGTH} characters."
            )

        qs = (
            Personas.objects.filter(
                Q(numero_documento__icontains=q)
                | Q(nombres__icontains=q)
                | Q(apellido_paterno__icontains=q)
                | Q(apellido_materno__icontains=q)
                | Q(nombre_completo__icontains=q)
            )
            .order_by("nombre_completo", "id_persona")
        )
        rows = list(qs[: PERSONA_LOOKUP_MAX_RESULTS + 1])
        truncated = len(rows) > PERSONA_LOOKUP_MAX_RESULTS
        if truncated:
            rows = rows[: PERSONA_LOOKUP_MAX_RESULTS]

        serializer = PersonaLookupSerializer(rows, many=True)
        return Response({"results": serializer.data, "truncated": truncated})


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

    @action(detail=False, methods=["get"], url_path="boleta")
    def boleta(self, request):
        queryset = self.queryset.filter(comprobante_id=BOLETA_COMPROBANTE_ID)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="factura")
    def factura(self, request):
        queryset = self.queryset.filter(comprobante_id=FACTURA_COMPROBANTE_ID)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="nota-credito")
    def nota_credito(self, request):
        queryset = self.queryset.filter(comprobante_id=NOTA_CREDITO_COMPROBANTE_ID)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="nota-debito")
    def nota_debito(self, request):
        queryset = self.queryset.filter(comprobante_id=NOTA_DEBITO_COMPROBANTE_ID)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class RecibosViewSet(DocumentReadViewSetMixin, ModelViewSet):
    serializer_class = RecibosSerializer
    read_serializer_class = RecibosReadSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Recibos.objects.all().order_by("-fecha_emision", "-id_recibo")

        user = self.request.user
        if user.negocio_id is not None:
            qs = qs.filter(negocio_id=user.negocio_id)

        params = self.request.query_params
        qs = apply_document_list_filters(qs, params)

        comprobante_id = (
            params.get("comprobante_id", "") or params.get("comprobante", "")
        ).strip()
        if comprobante_id:
            qs = qs.filter(comprobante_id=comprobante_id)

        serie = params.get("serie", "").strip()
        if serie:
            qs = qs.filter(serie__icontains=serie)

        numero = params.get("numero", "").strip()
        if numero:
            qs = qs.filter(numero=numero)

        anulada = params.get("anulada", "").strip().lower()
        if anulada in ("true", "false"):
            qs = qs.filter(anulada=(anulada == "true"))

        return qs

    def get_serializer_class(self):
        if self.action in ("list", "retrieve", "modificables"):
            return RecibosReadSerializer
        return RecibosSerializer

    @action(detail=False, methods=["get"], url_path="modificables")
    def modificables(self, request):
        """
        Facturas and boletas to select when creating NC/ND
        (newest first, paginated).

        Optional: ``comprobante_id=1|2``, ``serie``, ``numero``, ``aceptada_sunat``.
        """
        qs = Recibos.objects.all().order_by("-fecha_emision", "-id_recibo")

        user = request.user
        if user.negocio_id is not None:
            qs = qs.filter(negocio_id=user.negocio_id)

        qs = apply_document_list_filters(qs, request.query_params)
        qs = qs.filter(
            comprobante_id__in=(FACTURA_COMPROBANTE_ID, BOLETA_COMPROBANTE_ID),
            anulada=False,
        )

        params = request.query_params
        comprobante_id = (
            params.get("comprobante_id", "") or params.get("comprobante", "")
        ).strip()
        if comprobante_id in {
            str(FACTURA_COMPROBANTE_ID),
            str(BOLETA_COMPROBANTE_ID),
        }:
            qs = qs.filter(comprobante_id=int(comprobante_id))

        serie = params.get("serie", "").strip()
        if serie:
            qs = qs.filter(serie__icontains=serie)

        numero = params.get("numero", "").strip()
        if numero:
            qs = qs.filter(numero=numero)

        aceptada = params.get("aceptada_sunat", "").strip().lower()
        if aceptada in ("true", "1", "yes"):
            qs = qs.filter(aceptada_sunat=True)
        elif aceptada in ("false", "0", "no"):
            qs = qs.filter(aceptada_sunat=False)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self._read_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self._read_serializer(qs, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        user = self._linked_user_or_raise(request)
        serializer = CreateReciboSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lineas, fecha_emision, recibo_data = self._build_create_recibo_kwargs(
            serializer.validated_data
        )

        kardex_code = normalize_kardex(recibo_data.get("kardex"))
        if kardex_code is not None:
            recibo_data["kardex"] = kardex_code
            with transaction.atomic(using="default"):
                kardex = lock_kardex_for_billing(kardex_code)
                recibo, items, xml_result = create_recibo(
                    usuario_id=user.taxes_usuario_id,
                    negocio_id=user.negocio_id,
                    lineas=lineas,
                    fecha_emision=fecha_emision,
                    **recibo_data,
                )
                mark_kardex_as_billed(kardex)
        else:
            recibo, items, xml_result = create_recibo(
                usuario_id=user.taxes_usuario_id,
                negocio_id=user.negocio_id,
                lineas=lineas,
                fecha_emision=fecha_emision,
                **recibo_data,
            )

        payload = {"recibo": recibo, "items": items}
        sunat_raw = (xml_result or {}).get("sunat")
        if sunat_raw:
            outbox = get_active_outbox(
                kind=SunatOutbox.Kind.RECIBO,
                target_id=recibo.id_recibo,
            )
            payload["sunat"] = build_sunat_user_payload(sunat=sunat_raw, outbox=outbox)

        response = CreateReciboResponseSerializer(
            payload,
            context={
                **self.get_serializer_context(),
                **document_lookup_context([recibo]),
            },
        )
        return Response(response.data, status=status.HTTP_201_CREATED)

    def _linked_user_or_raise(self, request):
        user = request.user
        if user.taxes_usuario_id is None or user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (taxes_usuario_id / negocio_id)."
            )
        return user

    def _build_create_recibo_kwargs(self, validated_data):
        data = dict(validated_data)
        if "serie_documento_modificado_id" in data:
            data["serie_documento_modificado"] = data.pop(
                "serie_documento_modificado_id"
            )
        lineas = data.pop("lineas")
        fecha_emision = data.pop("fecha_emision", None)
        return lineas, fecha_emision, data

    @action(detail=False, methods=["get"], url_path="pendientes-sunat")
    def pendientes_sunat(self, request):
        user = request.user
        if user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (negocio_id)."
            )

        raw_fecha = request.query_params.get("fecha_emision", "").strip()
        if not raw_fecha:
            raise ValidationError("Query param 'fecha_emision' is required (YYYY-MM-DD).")

        fecha_emision = parse_date(raw_fecha)
        if not fecha_emision:
            raise ValidationError("fecha_emision must be YYYY-MM-DD.")

        qs = boletas_pendientes_sunat_queryset(
            negocio_id=user.negocio_id,
            fecha_emision=fecha_emision,
        )
        serializer = self._read_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="anular")
    def anular(self, request, pk=None):
        recibo = self.get_object()

        if recibo.anulada:
            raise ValidationError("El recibo ya está anulado.")

        serializer = AnularIngresoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        motivo = serializer.validated_data.get("motivo_baja") or "-"

        if recibo.comprobante_id == BOLETA_COMPROBANTE_ID:
            anular_boleta_recibo(recibo=recibo, motivo=motivo)
        elif recibo.comprobante_id in (NOTA_CREDITO_COMPROBANTE_ID, NOTA_DEBITO_COMPROBANTE_ID):
            comprobante_mod = (
                Comprobantes.objects.filter(
                    id_comprobante=recibo.tipo_recibo_modificado_id
                ).first()
                if recibo.tipo_recibo_modificado_id
                else None
            )
            if comprobante_mod and comprobante_mod.id_comprobante == BOLETA_COMPROBANTE_ID:
                anular_boleta_recibo(recibo=recibo, motivo=motivo)
            else:
                raise ValidationError(
                    "Las notas que modifican facturas se anulan mediante "
                    "POST /taxes/bajas/ (comunicación de baja SUNAT)."
                )
        elif recibo.comprobante_id == FACTURA_COMPROBANTE_ID:
            raise ValidationError(
                "Las facturas se anulan mediante POST /taxes/bajas/ "
                "(comunicación de baja SUNAT)."
            )
        else:
            raise ValidationError("Este comprobante no puede anularse por este endpoint.")

        recibo.refresh_from_db()
        response = self._read_serializer(recibo, many=False)
        return Response(response.data)

    @action(detail=True, methods=["post"], url_path="enviar-sunat")
    def enviar_sunat(self, request, pk=None):
        recibo = self.get_object()

        sunat_result = enviar_recibo_sunat(
            recibo_id=recibo.id_recibo,
            raise_on_failure=False,
        )
        if sunat_result.get("aceptada_sunat"):
            outbox = get_active_outbox(
                kind=SunatOutbox.Kind.RECIBO,
                target_id=recibo.id_recibo,
            )
            if outbox is not None:
                from taxes.services.sunat_outbox import mark_outbox_completed

                mark_outbox_completed(outbox)
        elif recibo_needs_sunat_retry(sunat_result):
            try:
                enqueue_recibo_send(
                    recibo_id=recibo.id_recibo,
                    last_error=str(sunat_result.get("msj_sunat") or ""),
                )
            except Exception:
                logger.exception(
                    "Failed to enqueue SUNAT retry for recibo_id=%s",
                    recibo.id_recibo,
                )

        recibo = Recibos.objects.using("postgres").get(pk=recibo.id_recibo)
        response = self._read_serializer(recibo, many=False)
        outbox = get_active_outbox(
            kind=SunatOutbox.Kind.RECIBO,
            target_id=recibo.id_recibo,
        )
        return Response(
            {
                **build_sunat_user_payload(sunat=sunat_result, outbox=outbox),
                "recibo": response.data,
            }
        )

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        self.get_object()
        pdf_bytes = generate_recibo_pdf(
            id_recibo=int(pk),
            negocio_id=request.user.negocio_id,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="recibo-{pk}.pdf"'
        return response


class IngresosViewSet(DocumentReadViewSetMixin, ModelViewSet):
    serializer_class = IngresosSerializer
    read_serializer_class = IngresosReadSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Ingresos.objects.all().order_by("-fecha_emision", "-id_ingreso")

        user = self.request.user
        if user.negocio_id is not None:
            qs = qs.filter(negocio_id=user.negocio_id)

        if self.action == "list":
            qs = qs.filter(canjeada=False)

        return apply_document_list_filters(qs, self.request.query_params)

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return IngresosReadSerializer
        return IngresosSerializer

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

        data = dict(serializer.validated_data)
        kardex_code = normalize_kardex(data.get("kardex"))
        if kardex_code is not None:
            data["kardex"] = kardex_code
            with transaction.atomic(using="default"):
                kardex = lock_kardex_for_billing(kardex_code)
                ingreso, detalles = create_control_interno(
                    data,
                    usuario_id=user.taxes_usuario_id,
                    negocio_id=user.negocio_id,
                )
                mark_kardex_as_billed(kardex)
        else:
            ingreso, detalles = create_control_interno(
                data,
                usuario_id=user.taxes_usuario_id,
                negocio_id=user.negocio_id,
            )

        response = ControlInternoResponseSerializer(
            ingreso,
            context={"detalles": detalles},
        )
        return Response(response.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="anular")
    def anular(self, request, pk=None):
        ingreso = self.get_object()

        if ingreso.anulada:
            raise ValidationError("El ingreso ya está anulado.")

        serializer = AnularIngresoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ingreso.anulada = True
        ingreso.motivo_baja = serializer.validated_data.get("motivo_baja") or "-"
        ingreso.fecha_baja = timezone.localdate()
        ingreso.save(
            update_fields=["anulada", "motivo_baja", "fecha_baja"],
        )

        response = self._read_serializer(ingreso, many=False)
        return Response(response.data)

    @action(detail=True, methods=["post"], url_path="canjear")
    def canjear(self, request, pk=None):
        ingreso = self.get_object()
        user = request.user
        if user.taxes_usuario_id is None or user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (taxes_usuario_id / negocio_id)."
            )

        serializer = CanjeIngresoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ingreso, recibo, items = canjear_ingreso(
            ingreso_id=ingreso.id_ingreso,
            usuario_id=user.taxes_usuario_id,
            negocio_id=user.negocio_id,
            serie=data["serie"],
            observaciones=data.get("observaciones") or "",
            fecha_emision=data.get("fecha_emision"),
        )

        response = CanjeResponseSerializer(
            {
                "ingreso": ingreso,
                "recibo": recibo,
                "items": items,
            },
            context={
                **self.get_serializer_context(),
                **document_lookup_context([ingreso, recibo]),
            },
        )
        return Response(response.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        self.get_object()
        pdf_bytes = generate_ingreso_pdf(
            id_ingreso=int(pk),
            negocio_id=request.user.negocio_id,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="ingreso-{pk}.pdf"'
        return response


class ResumenesViewSet(DocumentReadViewSetMixin, ModelViewSet):
    serializer_class = ResumenesSerializer
    read_serializer_class = ResumenesReadSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]
    lookup_field = "id_resumen"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Resumenes.objects.all().order_by("-fecha_resumen", "-id_resumen")
        params = self.request.query_params
        user = self.request.user

        comprobante_id = (
            params.get("comprobante_id", "") or params.get("comprobante", "")
        ).strip()
        if comprobante_id and user.negocio_id is not None:
            resumen_ids = (
                Recibos.objects.filter(
                    negocio_id=user.negocio_id,
                    comprobante_id=comprobante_id,
                    resumen_id__isnull=False,
                )
                .values_list("resumen_id", flat=True)
                .distinct()
            )
            qs = qs.filter(id_resumen__in=resumen_ids)

        fecha_resumen = params.get("fecha_resumen", "").strip()
        if fecha_resumen:
            parsed = parse_date(fecha_resumen)
            if parsed:
                qs = qs.filter(fecha_resumen=parsed)

        fecha_desde = params.get("fecha_resumen_desde", "").strip()
        if fecha_desde:
            parsed = parse_date(fecha_desde)
            if parsed:
                qs = qs.filter(fecha_resumen__gte=parsed)

        fecha_hasta = params.get("fecha_resumen_hasta", "").strip()
        if fecha_hasta:
            parsed = parse_date(fecha_hasta)
            if parsed:
                qs = qs.filter(fecha_resumen__lte=parsed)

        usuario_id = params.get("usuario_id", "").strip()
        if usuario_id:
            qs = qs.filter(usuario_id=usuario_id)

        q = params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(ticket_sunat__icontains=q) | Q(denominacion__icontains=q)
            )

        enviada_sunat = params.get("enviada_sunat", "").strip().lower()
        if enviada_sunat in ("true", "false"):
            qs = qs.filter(enviada_sunat=(enviada_sunat == "true"))

        aceptada_sunat = params.get("aceptada_sunat", "").strip().lower()
        if aceptada_sunat in ("true", "false"):
            qs = qs.filter(aceptada_sunat=(aceptada_sunat == "true"))

        return qs

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return ResumenesReadSerializer
        return ResumenesSerializer

    def create(self, request, *args, **kwargs):
        user = request.user
        if user.taxes_usuario_id is None or user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (taxes_usuario_id / negocio_id)."
            )

        serializer = CreateResumenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic(using=POSTGRES_DB):
            resumen, recibos = create_resumen(
                fecha_resumen=data["fecha_comunicacion"],
                fecha_emision=data["fecha_emision"],
                comprobante_id=data["comprobante_id"],
                recibo_ids=data["recibo_ids"],
                usuario_id=user.taxes_usuario_id,
                negocio_id=user.negocio_id,
            )

        return self._respond_after_resumen_sunat(resumen)

    @action(detail=False, methods=["post"], url_path="enviar-boleta")
    def enviar_boleta(self, request):
        """Create a resumen with one boleta and send it to SUNAT (sendSummary)."""
        user = request.user
        if user.taxes_usuario_id is None or user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (taxes_usuario_id / negocio_id)."
            )

        serializer = EnviarBoletaResumenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        resumen, _recibos = create_resumen_for_single_recibo(
            recibo_id=data["recibo_id"],
            usuario_id=user.taxes_usuario_id,
            negocio_id=user.negocio_id,
            fecha_comunicacion=data.get("fecha_comunicacion"),
        )
        return self._respond_after_resumen_sunat(resumen)

    def _respond_after_resumen_sunat(self, resumen):
        # sendSummary only in the request (ticket is instant). Never block the UI
        # on getStatus — CDR polling belongs in Celery (resumen ≠ factura sendBill).
        sunat_result = procesar_resumen_sunat(
            resumen_id=resumen.id_resumen,
            consultar_ticket=False,
            raise_on_failure=False,
        )

        envio = sunat_result.get("sunat_envio") or {}
        ticket = (envio.get("ticket") or "").strip()
        if ticket:
            try:
                enqueue_resumen_send(
                    resumen_id=resumen.id_resumen,
                    last_error="CDR pendiente de consulta (ticket emitido).",
                    phase=SunatOutbox.Phase.POLL,
                    metadata={"ticket": ticket},
                )
            except Exception:
                logger.exception(
                    "Failed to enqueue SUNAT ticket poll for resumen_id=%s",
                    resumen.id_resumen,
                )
        elif resumen_needs_sunat_retry(sunat_result):
            try:
                enqueue_resumen_send(
                    resumen_id=resumen.id_resumen,
                    last_error=str(envio.get("msj_sunat") or ""),
                    phase=SunatOutbox.Phase.SEND,
                )
            except Exception:
                logger.exception(
                    "Failed to enqueue SUNAT retry for resumen_id=%s",
                    resumen.id_resumen,
                )

        resumen = Resumenes.objects.using(POSTGRES_DB).get(pk=resumen.id_resumen)
        recibos = list(
            Recibos.objects.using(POSTGRES_DB)
            .filter(resumen_id=resumen.id_resumen)
            .order_by("id_recibo")
        )

        flat_sunat = {
            **envio,
            "en_proceso": bool(ticket) and not resumen.aceptada_sunat,
            "enviada_sunat": bool(ticket) or bool(envio.get("enviada_sunat")),
            "aceptada_sunat": bool(resumen.aceptada_sunat),
            "ticket": ticket or envio.get("ticket") or "",
        }

        outbox = get_active_outbox(
            kind=SunatOutbox.Kind.RESUMEN,
            target_id=resumen.id_resumen,
        )
        sunat_payload = build_sunat_user_payload(sunat=flat_sunat, outbox=outbox)
        payload = {
            "resumen": resumen,
            "recibos": recibos,
            "sunat": {**sunat_result, **sunat_payload},
        }

        response = CreateResumenResponseSerializer(
            payload,
            context={
                **self.get_serializer_context(),
                **document_lookup_context([resumen, *recibos]),
            },
        )
        return Response(response.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        resumen = self.get_object()
        recibos = list(
            Recibos.objects.filter(resumen_id=resumen.id_resumen).order_by("id_recibo")
        )
        response = CreateResumenResponseSerializer(
            {"resumen": resumen, "recibos": recibos},
            context={
                **self.get_serializer_context(),
                **document_lookup_context([resumen, *recibos]),
            },
        )
        return Response(response.data)

    @action(detail=True, methods=["post"], url_path="consultar-ticket")
    def consultar_ticket(self, request, id_resumen=None):
        resumen = self.get_object()
        serializer = ConsultarTicketResumenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ticket = (data.get("ticket") or "").strip() or None
        # One getStatus call only — never block the UI with multi-poll loops.
        sunat_result = consultar_ticket_resumen(
            resumen_id=resumen.id_resumen,
            ticket=ticket,
            max_polls=1,
            poll_interval_seconds=1.0,
            raise_on_failure=False,
        )

        resumen = Resumenes.objects.using(POSTGRES_DB).get(pk=resumen.id_resumen)
        recibos = list(
            Recibos.objects.using(POSTGRES_DB)
            .filter(resumen_id=resumen.id_resumen)
            .order_by("id_recibo")
        )
        response = CreateResumenResponseSerializer(
            {"resumen": resumen, "recibos": recibos, "sunat": sunat_result},
            context={
                **self.get_serializer_context(),
                **document_lookup_context([resumen, *recibos]),
            },
        )
        return Response(response.data)

    @action(detail=False, methods=["get"], url_path="recibos-pendientes")
    def recibos_pendientes(self, request):
        user = request.user
        if user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (negocio_id)."
            )

        params = request.query_params
        comprobante_id = int(
            (params.get("comprobante_id") or params.get("comprobante") or "2").strip()
        )
        fecha_emision = None
        raw_fecha = params.get("fecha_emision", "").strip()
        if raw_fecha:
            fecha_emision = parse_date(raw_fecha)
            if not fecha_emision:
                raise ValidationError("fecha_emision must be YYYY-MM-DD.")

        qs = recibos_pendientes_queryset(
            negocio_id=user.negocio_id,
            comprobante_id=comprobante_id,
            fecha_emision=fecha_emision,
        )
        serializer = RecibosReadSerializer(
            qs,
            many=True,
            context={
                **self.get_serializer_context(),
                **document_lookup_context(list(qs)),
            },
        )
        return Response(serializer.data)


class BajasViewSet(DocumentReadViewSetMixin, ModelViewSet):
    serializer_class = BajasSerializer
    read_serializer_class = BajasReadSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]
    lookup_field = "id_baja"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Bajas.objects.all().order_by("-fecha_baja", "-id_baja")
        params = self.request.query_params
        user = self.request.user

        comprobante_id = (
            params.get("comprobante_id", "") or params.get("comprobante", "")
        ).strip()
        if comprobante_id and user.negocio_id is not None:
            baja_ids = (
                Recibos.objects.filter(
                    negocio_id=user.negocio_id,
                    comprobante_id=comprobante_id,
                    baja_id__isnull=False,
                )
                .values_list("baja_id", flat=True)
                .distinct()
            )
            qs = qs.filter(id_baja__in=baja_ids)

        fecha_baja = params.get("fecha_baja", "").strip()
        if fecha_baja:
            parsed = parse_date(fecha_baja)
            if parsed:
                qs = qs.filter(fecha_baja=parsed)

        enviada_sunat = params.get("enviada_sunat", "").strip().lower()
        if enviada_sunat in ("true", "false"):
            qs = qs.filter(enviada_sunat=(enviada_sunat == "true"))

        aceptada_sunat = params.get("aceptada_sunat", "").strip().lower()
        if aceptada_sunat in ("true", "false"):
            qs = qs.filter(aceptada_sunat=(aceptada_sunat == "true"))

        return qs

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return BajasReadSerializer
        return BajasSerializer

    def create(self, request, *args, **kwargs):
        user = request.user
        if user.taxes_usuario_id is None or user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (taxes_usuario_id / negocio_id)."
            )

        serializer = CreateBajaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic(using=POSTGRES_DB):
            baja, recibos = create_baja(
                fecha_emision=data["fecha_emision"],
                comprobante_id=data["comprobante_id"],
                recibo_ids=data["recibo_ids"],
                motivo=data["motivo"],
                usuario_id=user.taxes_usuario_id,
                negocio_id=user.negocio_id,
            )

            sunat_result = procesar_baja_sunat(
                baja_id=baja.id_baja,
                max_polls=data.get("max_polls", 10),
                poll_interval_seconds=data.get("poll_interval_seconds", 3.0),
                raise_on_failure=True,
            )
            baja = Bajas.objects.using(POSTGRES_DB).get(pk=baja.id_baja)
            recibos = list(
                Recibos.objects.using(POSTGRES_DB)
                .filter(baja_id=baja.id_baja)
                .order_by("id_recibo")
            )

        response = CreateBajaResponseSerializer(
            {"baja": baja, "recibos": recibos, "sunat": sunat_result},
            context={
                **self.get_serializer_context(),
                **document_lookup_context([baja, *recibos]),
            },
        )
        return Response(response.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        baja = self.get_object()
        recibos = list(
            Recibos.objects.filter(baja_id=baja.id_baja).order_by("id_recibo")
        )
        response = CreateBajaResponseSerializer(
            {"baja": baja, "recibos": recibos},
            context={
                **self.get_serializer_context(),
                **document_lookup_context([baja, *recibos]),
            },
        )
        return Response(response.data)

    @action(detail=True, methods=["post"], url_path="consultar-ticket")
    def consultar_ticket(self, request, id_baja=None):
        baja = self.get_object()
        serializer = ConsultarTicketBajaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        ticket = (data.get("ticket") or "").strip() or None
        sunat_result = consultar_ticket_baja(
            baja_id=baja.id_baja,
            ticket=ticket,
            max_polls=data.get("max_polls", 10),
            poll_interval_seconds=data.get("poll_interval_seconds", 3.0),
            raise_on_failure=False,
        )

        baja = Bajas.objects.using(POSTGRES_DB).get(pk=baja.id_baja)
        recibos = list(
            Recibos.objects.using(POSTGRES_DB)
            .filter(baja_id=baja.id_baja)
            .order_by("id_recibo")
        )
        response = CreateBajaResponseSerializer(
            {"baja": baja, "recibos": recibos, "sunat": sunat_result},
            context={
                **self.get_serializer_context(),
                **document_lookup_context([baja, *recibos]),
            },
        )
        return Response(response.data)

    @action(detail=False, methods=["get"], url_path="recibos-pendientes")
    def recibos_pendientes(self, request):
        user = request.user
        if user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (negocio_id)."
            )

        params = request.query_params
        comprobante_id = int(
            (params.get("comprobante_id") or params.get("comprobante") or "1").strip()
        )
        fecha_emision = None
        raw_fecha = params.get("fecha_emision", "").strip()
        if raw_fecha:
            fecha_emision = parse_date(raw_fecha)
            if not fecha_emision:
                raise ValidationError("fecha_emision must be YYYY-MM-DD.")

        qs = recibos_pendientes_baja_queryset(
            negocio_id=user.negocio_id,
            comprobante_id=comprobante_id,
            fecha_emision=fecha_emision,
        )
        serializer = RecibosReadSerializer(
            qs,
            many=True,
            context={
                **self.get_serializer_context(),
                **document_lookup_context(list(qs)),
            },
        )
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="recibos-anulados")
    def recibos_anulados(self, request):
        user = request.user
        if user.negocio_id is None:
            raise ValidationError(
                "El usuario no está vinculado a taxes (negocio_id)."
            )

        params = request.query_params
        comprobante_id = int(
            (params.get("comprobante_id") or params.get("comprobante") or "2").strip()
        )
        qs = recibos_anulados_queryset(
            negocio_id=user.negocio_id,
            comprobante_id=comprobante_id,
        )
        serializer = RecibosReadSerializer(
            qs,
            many=True,
            context={
                **self.get_serializer_context(),
                **document_lookup_context(list(qs)),
            },
        )
        return Response(serializer.data)


class IngresosDetallesViewSet(ModelViewSet):
    serializer_class = IngresosDetallesSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = IngresosDetalles.objects.all().order_by("-id_ingreso_detalle")
        ingreso_id = self.request.query_params.get("ingreso_id", "").strip()
        if ingreso_id:
            qs = qs.filter(ingreso_id=ingreso_id)
        return qs


class ItemsRecibosViewSet(ModelViewSet):
    serializer_class = ItemsRecibosSerializer
    pagination_class = KardexPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ItemsRecibos.objects.all().order_by("-id_item")
        recibo_id = self.request.query_params.get("recibo_id", "").strip()
        if recibo_id:
            qs = qs.filter(recibo_id=recibo_id)
        return qs


class UsuariosViewSet(ReadOnlyModelViewSet):
    serializer_class = UsuariosSerializer
    permission_classes = [IsAuthenticated, IsSuperuser]
    # pagination_class = KardexPagination
    lookup_field = "id_usuario"

    def create(self, request, *args, **kwargs):
        serializer = CreateTaxesUsuarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = create_taxes_usuario(actor=request.user, **serializer.validated_data)
        response = CreateTaxesUsuarioResponseSerializer(result)
        return Response(response.data, status=status.HTTP_201_CREATED)

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
