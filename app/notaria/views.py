from rest_framework.viewsets import ModelViewSet
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from ducumentation.protocolares.EscrituraPublicaDocumentService import (
    EscriturasPublicasReportService,
)
from ducumentation.protocolares.TransferenciasVehicularesService import (
    TransferenciasVehicularesReportService,
)
from ducumentation.protocolares.NoContenciososService import (
    NoContenciososReportService,
)
from ducumentation.protocolares.GarantiasService import (
    GarantiasReportService,
)
from ducumentation.protocolares.TestamentosService import (
    TestamentosReportService,
)
from .services.pdt_libros_service import PdtLibrosService

from ducumentation.extraprotocolares.cartas_notariales import CartasNotarialesReportService
from ducumentation.extraprotocolares.permiso_viajes import PermisosViajeReportService
from ducumentation.extraprotocolares.cert_domiciliarios import CertDomiciliariosReportService
from datetime import datetime
from typing import List

from . import models
from . import serializers
from . import pagination
from rest_framework.decorators import action
from io import BytesIO

from django.http import FileResponse, Http404
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from django.db.models import Q, Max, F, Func, Value
from django.db.models.functions import Cast, Substr
from django.db import models as django_models
from django.db import transaction
from django.db import connection

from collections import defaultdict
from . import utils
from datetime import datetime

from django.utils import timezone
from datetime import datetime
import logging
from .services.uif_report_service import UifReportService
from .services.pdt_file_service import PdtFileService
from .services.pdt_escrituras_service import PdtEscriturasService
from .services.pdt_vehiculares_service import PdtVehicularesService
from .services.pdt_garantias_service import PdtGarantiasService
from .constants import get_kardex_abbreviation_map
from ducumentation.storage import (
    build_object_key,
    default_folder_plantillas,
    docx_filename_from_name_template,
    full_object_key_from_stored_relative,
    get_r2_bucket,
    get_s3_client,
    object_key_for_tpl_template_row,
    read_bytes_from_r2,
    sanitize_copy_suffix_base,
    upload_fileobj_to_r2,
    validate_folder_path,
)

logger = logging.getLogger(__name__)


"""
ViewSets for the Notaria app.
These viewsets define the views for the Notaria app.
They are used to handle HTTP requests and responses.
They are also used to define the URL patterns for the Notaria app.
"""


def _normalize_condicion_entries(condicion_value):
    """
    Normalize condicion payload strings like:
    - '001.1/002.1/'
    into ordered unique tuples: [('001', '1'), ('002', '1')]
    """
    if not condicion_value:
        return []

    raw_entries = str(condicion_value).split("/")
    normalized = []
    seen = set()

    for raw in raw_entries:
        raw = (raw or "").strip()
        if not raw or "." not in raw:
            continue
        idcondicion, item = raw.split(".", 1)
        idcondicion = idcondicion.strip()
        item = item.strip()
        if not idcondicion or not item:
            continue
        key = (idcondicion, item)
        if key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized


def _contratantesxacto_formulario_from_acto(condicion):
    """
    ``contratantesxacto.formulario`` is NOT NULL in legacy MariaDB; ``actocondicion.formulario``
    may be NULL when conditions are created without that field.
    """
    v = getattr(condicion, "formulario", None)
    if v is None:
        return ""
    s = str(v).strip()
    return s[:2] if len(s) > 2 else s


def _reset_sisgen_for_kardex(kardex_code):
    if not kardex_code:
        return
    models.Kardex.objects.filter(kardex=kardex_code).exclude(estado_sisgen=0).update(
        estado_sisgen=0
    )


def _refresh_kardex_fechaconclusion_from_contratantes(kardex_code):
    """
    Set kardex.fechaconclusion to the most recent contratante.fechafirma for this kardex.
    Supports both DD/MM/YYYY and YYYY-MM-DD stored date strings.
    """
    if not kardex_code:
        return

    latest_dt = None
    latest_raw = ""
    fecha_rows = models.Contratantes.objects.filter(kardex=kardex_code).values_list(
        "fechafirma", flat=True
    )

    for fecha in fecha_rows:
        raw = str(fecha or "").strip()
        if not raw:
            continue
        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            continue
        if latest_dt is None or parsed > latest_dt:
            latest_dt = parsed
            latest_raw = raw

    if latest_dt is None:
        models.Kardex.objects.filter(kardex=kardex_code).update(fechaconclusion="")
        return

    models.Kardex.objects.filter(kardex=kardex_code).update(fechaconclusion=latest_raw)


def _sync_cliente_from_cliente2(cliente2_obj, force_overrides=None):
    """
    Keep legacy `cliente` row aligned with updates made on `cliente2`.

    We mirror only shared columns between both models and upsert by `idcliente`.
    """
    if not cliente2_obj:
        return

    idcliente = str(getattr(cliente2_obj, "idcliente", "") or "").strip()
    numdoc = str(getattr(cliente2_obj, "numdoc", "") or "").strip()
    if not idcliente and not numdoc:
        return

    cliente_fields = {
        f.name
        for f in models.Cliente._meta.concrete_fields
        if f.name != "idcliente"
    }
    cliente2_fields = {
        f.name
        for f in models.Cliente2._meta.concrete_fields
        if f.name not in {"idcliente", "idcontratante"}
    }
    shared = cliente_fields & cliente2_fields
    payload = {name: getattr(cliente2_obj, name) for name in shared}
    if force_overrides:
        payload.update({k: v for k, v in force_overrides.items() if k in shared})

    # Link by numdoc first (requested behavior); fallback to cliente2.idcliente.
    target = None
    if numdoc:
        q = models.Cliente.objects.filter(numdoc=numdoc)
        target = q.order_by("-idcliente").first()
        if target is not None:
            # Keep all duplicated cliente rows for this numdoc in sync.
            q.update(**payload)

    if target is not None:
        if str(getattr(cliente2_obj, "idcliente", "") or "").strip() != target.idcliente:
            # Keep linkage aligned after resolving by numdoc.
            models.Cliente2.objects.filter(pk=cliente2_obj.pk).update(idcliente=target.idcliente)
        return

    # No cliente by numdoc; fallback to historical idcliente linkage.
    if not idcliente:
        return
    models.Cliente.objects.update_or_create(idcliente=idcliente, defaults=payload)


class UsuariosViewSet(ModelViewSet):
    """
    ViewSet for the Usuarios model.
    """

    queryset = models.Usuarios.objects.all()
    serializer_class = serializers.UsuariosSerializer
    permission_classes = [IsAuthenticated]


class PermisosUsuariosViewSet(ModelViewSet):
    """
    ViewSet for the PermisosUsuarios model.
    """

    queryset = models.PermisosUsuarios.objects.all()
    serializer_class = serializers.PermisosUsuariosSerializer
    permission_classes = [IsAuthenticated]


class KardexViewSet(ModelViewSet):
    """
    ViewSet for the Kardex model.

    Unified filtering through query parameters:
    - correlative: Filter by kardex prefix (e.g., "2025" for kardex starting with "2025")
    - name: Filter by client name (searches nombre, apepat, apemat, primom, segnom)
    - document: Filter by client document number
    - numescritura: Filter by escritura number
    - idtipkar: Filter by kardex type
    - dateFrom/dateTo/dateType: Filter by fechaingreso date range
    """

    serializer_class = serializers.KardexSerializer
    pagination_class = pagination.KardexPagination
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Base queryset - filtering is handled in list() method.
        """
        return models.Kardex.objects.all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.CreateKardexSerializer
        return serializers.KardexSerializer

    def list(self, request, *args, **kwargs):
        """
        List all Kardex objects with comprehensive filtering.
        """
        # Get filter parameters
        correlative = request.query_params.get("correlative", "")
        name = request.query_params.get("name", "")
        document = request.query_params.get("document", "")
        numescritura = request.query_params.get("numescritura", "")
        idtipkar = request.query_params.get("idtipkar", "")
        dateFrom = request.query_params.get("dateFrom", "")
        dateTo = request.query_params.get("dateTo", "")
        dateType = request.query_params.get("dateType", "")
        index_report = request.query_params.get("indexReport", "")

        # Start with base queryset
        queryset = self.get_queryset()

        # Apply idtipkar filter if provided
        if idtipkar:
            queryset = queryset.filter(idtipkar=idtipkar)

        print('index_report', index_report)
        if index_report:
            queryset = queryset.filter(numescritura__gt='')

        # Apply date filters
        if dateType == "fechaingreso":
            if dateFrom and dateTo:
                queryset = queryset.filter(fechaingreso__range=(dateFrom, dateTo))
            elif dateFrom:
                queryset = queryset.filter(fechaingreso__gte=dateFrom)
            elif dateTo:
                queryset = queryset.filter(fechaingreso__lte=dateTo)

        if dateTo and dateFrom:
            queryset = queryset.filter(fechaescritura__range=(dateFrom, dateTo))
        elif dateFrom:
            queryset = queryset.filter(fechaescritura__gte=dateFrom)
        elif dateTo:
            queryset = queryset.filter(fechaescritura__lte=dateTo)

        # Apply correlative filter (kardex__startswith)
        if correlative:
            queryset = queryset.filter(kardex__startswith=correlative)

        # Apply numescritura filter
        if numescritura:
            queryset = queryset.filter(numescritura=numescritura)

        # Apply name/document filters through related models
        if name or document:
            # Get clientes that match name or document criteria
            cliente_filters = Q()
            if name:
                cliente_filters |= (
                    Q(nombre__icontains=name)
                    | Q(apepat__icontains=name)
                    | Q(apemat__icontains=name)
                    | Q(prinom__icontains=name)
                    | Q(segnom__icontains=name)
                )
            if document:
                cliente_filters |= Q(numdoc__icontains=document)

            # Get contratantes for matching clientes
            matching_clientes = models.Cliente2.objects.filter(cliente_filters).values_list(
                "idcontratante", flat=True
            )
            matching_kardex = models.Contratantes.objects.filter(
                idcontratante__in=matching_clientes
            ).values_list("kardex", flat=True)

            # Filter kardex by matching kardex IDs
            queryset = queryset.filter(kardex__in=matching_kardex)

        # Order by fechaingreso (newest first)
        queryset = queryset.order_by("-idkardex")

        # Paginate the filtered queryset
        page_kardex = self.paginate_queryset(queryset)

        # Prepare optimized data maps for serializer context
        user_ids = set(obj.idusuario for obj in page_kardex)
        kardex_ids = set(obj.kardex for obj in page_kardex)

        usuarios_map = {
            u.idusuario: u for u in models.Usuarios.objects.filter(idusuario__in=user_ids)
        }

        contratantes = models.Contratantes.objects.filter(kardex__in=kardex_ids).values(
            "idcontratante", "kardex"
        )

        contratantes_map = defaultdict(list)
        for c in contratantes:
            contratantes_map[c["kardex"]].append(c["idcontratante"])

        contratante_ids = set(c["idcontratante"] for c in contratantes)

        clientes_map = {
            c["idcontratante"]: c
            for c in models.Cliente2.objects.filter(idcontratante__in=contratante_ids).values(
                "idcontratante", "nombre", "numdoc", "razonsocial"
            )
        }

        # Serialize with context
        serializer = self.get_serializer(
            page_kardex,
            many=True,
            context={
                "usuarios_map": usuarios_map,
                "contratantes_map": contratantes_map,
                "clientes_map": clientes_map,
            },
        )

        return self.get_paginated_response(serializer.data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        Override the update method to handle the update of the tipo de actos.
        """

        instance = self.get_object()
        data = request.data
        codactos = data.get("codactos", "")
        id_tipo_actos_array = [codactos[i : i + 3] for i in range(0, len(codactos), 3)]
        set_data = set(id_tipo_actos_array)
        id_tipo_actos_array_instance = [
            instance.codactos[i : i + 3] for i in range(0, len(instance.codactos), 3)
        ]
        set_instance = set(id_tipo_actos_array_instance)

        only_in_set_data = set_data - set_instance
        only_in_set_conditions = set_instance - set_data

        for id_tipo_acto in only_in_set_conditions:
            try:
                tipo_acto = models.Tiposdeacto.objects.get(idtipoacto=id_tipo_acto)
            except models.Tiposdeacto.DoesNotExist:
                return Response({"error": "Tipo de acto no encontrado."}, status=404)

            # Check if there are any contratantes using this tipo_acto
            if models.Contratantesxacto.objects.filter(
                kardex=instance.kardex, idtipoacto=id_tipo_acto
            ).exists():
                return Response(
                    {
                        "error": "No se puede eliminar el tipo de acto porque hay contratantes asociados."
                    },
                    status=400,
                )

            # chec if there any patrimonial records using this tipo_acto
            if models.Patrimonial.objects.filter(
                kardex=instance.kardex, idtipoacto=id_tipo_acto
            ).exists():
                return Response(
                    {
                        "error": "No se puede eliminar el tipo de acto porque hay patrimoniales asociados."
                    },
                    status=400,
                )

            # If no contratantes are using this tipo_acto, delete the detalle acto
            models.DetalleActosKardex.objects.filter(
                kardex=instance.kardex, idtipoacto=id_tipo_acto
            ).delete()

        for id_tipo_acto in only_in_set_data:
            try:
                tipo_acto = models.Tiposdeacto.objects.get(idtipoacto=id_tipo_acto)
            except models.Tiposdeacto.DoesNotExist:
                return Response({"error": "Tipo de acto no encontrado."}, status=404)

            detalle_data = {
                "kardex": instance.kardex,
                "idtipoacto": id_tipo_acto,
                "actosunat": tipo_acto.actosunat,
                "actouif": tipo_acto.actouif,
                "idtipkar": int(instance.idtipkar),
                "desacto": tipo_acto.desacto,
            }

            models.DetalleActosKardex.objects.create(**detalle_data)

        reservation_id = request.data.get("signatum_reservation_id") or request.query_params.get(
            "signatum_reservation_id"
        )
        rid = None
        if reservation_id not in (None, ""):
            try:
                rid = int(reservation_id)
            except (TypeError, ValueError):
                raise ValidationError(
                    {"signatum_reservation_id": "Must be a valid integer."},
                )

        response = super().update(request, *args, **kwargs)
        kardex_instance = self.get_object()
        _reset_sisgen_for_kardex(kardex_instance.kardex)
        if isinstance(getattr(response, "data", None), dict):
            response.data["estado_sisgen"] = 0

        if rid is not None:
            from signatum.services import finalize_notarization_from_reservation

            finalize_notarization_from_reservation(
                kardex_instance=kardex_instance,
                reservation_id=rid,
                user=request.user,
            )

        return response

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Override the create method to generate a Kardex number.
        """
        data = request.data.copy()
        idtipkar = data.get("idtipkar")
        fechaingreso = data.get("fechaingreso")
        idtipoactos = data.get("codactos")

        # Validate required fields
        if not idtipkar or not fechaingreso:
            return Response({"error": "Missing required fields"}, status=400)

        # Extract year from fechaingreso supporting DD/MM/YYYY and YYYY-MM-DD
        fechaingreso_str = str(fechaingreso or "").strip()
        try:
            if "/" in fechaingreso_str:
                anio = fechaingreso_str.split("/")[-1]
            elif "-" in fechaingreso_str:
                # Expected API/storage format: YYYY-MM-DD
                anio = fechaingreso_str.split("-")[0]
            else:
                return Response({"error": "Invalid fechaingreso format"}, status=400)
            if not anio.isdigit() or len(anio) != 4:
                return Response({"error": "Invalid fechaingreso format"}, status=400)
        except Exception:
            return Response({"error": "Invalid fechaingreso format"}, status=400)

        # Get abbreviation based on tipoescritura
        abreviatura_map = get_kardex_abbreviation_map()
        abreviatura = abreviatura_map.get(str(idtipkar))
        if not abreviatura:
            return Response({"error": "Invalid tipoescritura"}, status=400)

        # Query last Kardex number for this tipo and target year.
        # Use kardex suffix "-YYYY" so yearly reset does not depend on fechaingreso storage format.
        last_kardex = (
            models.Kardex.objects.filter(
                idtipkar=idtipkar,
                kardex__startswith=abreviatura,
                kardex__endswith=f"-{anio}",
            )
            .annotate(
                numeric_part=Cast(
                    Substr(F("kardex"), len(abreviatura) + 1, 4),
                    output_field=django_models.IntegerField(),
                )
            )
            .order_by("-numeric_part")
            .first()
        )

        # # Extract the numeric part of the last Kardex number
        if last_kardex and last_kardex.kardex:
            try:
                numeric_part = int("".join(filter(str.isdigit, last_kardex.kardex.split("-")[0])))
            except ValueError:
                numeric_part = 0
        else:
            numeric_part = 0  # Start from 0 if no Kardex exists
        # # Increment the numeric part and generate the new Kardex number
        new_kardex_number = f"{abreviatura}{numeric_part + 1}-{anio}"

        # # Save the new Kardex record

        data["kardex"] = new_kardex_number
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        id_tipo_actos_array = [idtipoactos[i : i + 3] for i in range(0, len(idtipoactos), 3)]
        for idtipoacto in id_tipo_actos_array:
            try:
                tipo_acto = models.Tiposdeacto.objects.get(idtipoacto=idtipoacto)
            except models.Tiposdeacto.DoesNotExist:
                return Response({"error": "Tipo de acto no encontrado."}, status=404)

            detalle_data = {
                "kardex": new_kardex_number,
                "idtipoacto": idtipoacto,
                "actosunat": tipo_acto.actosunat,
                "actouif": tipo_acto.actouif,
                "idtipkar": int(idtipkar),
                "desacto": tipo_acto.desacto,
            }

            models.DetalleActosKardex.objects.create(**detalle_data)

        return Response(serializer.data, status=201)

    @action(detail=False, methods=["get"], url_path="escrituras-cronologico")
    def escrituras_cronologico(self, request):
        """
        Reporte Cronológico - generates a report of the kardex records.
        parameters:
        - initialDate: YYYY-MM-DD
        - finalDate: YYYY-MM-DD
        - tipo_documento: 'EXCEL' or 'WORD'
        """
        print(f"DEBUG: Reporte Cronológico - generating report")
        initialDate = request.query_params.get("initialDate")
        finalDate = request.query_params.get("finalDate")
        tipo_documento = request.query_params.get("tipo_documento")
        service = EscriturasPublicasReportService()
        if tipo_documento == 'EXCEL':
            response = service.generate_excel_report(desde=initialDate, hasta=finalDate)
        else:
            response = service.generate_word_report(desde=initialDate, hasta=finalDate)
        return response

    @action(detail=False, methods=["get"], url_path="transferencias-cronologico")
    def transferencias_cronologico(self, request):
        """
        Reporte Cronológico - generates a report of the kardex records.
        parameters:
        - initialDate: YYYY-MM-DD
        - finalDate: YYYY-MM-DD
        - tipo_documento: 'EXCEL' or 'WORD'
        """
        print(f"DEBUG: Reporte Cronológico - generating report")
        initialDate = request.query_params.get("initialDate")
        finalDate = request.query_params.get("finalDate")
        tipo_documento = request.query_params.get("tipo_documento")
        service = TransferenciasVehicularesReportService()
        if tipo_documento == 'EXCEL':
            response = service.generate_excel_report(desde=initialDate, hasta=finalDate)
        else:
            response = service.generate_word_report(desde=initialDate, hasta=finalDate)
        return response

    @action(detail=False, methods=["get"], url_path="no-contenciosos-cronologico")
    def no_contenciosos_cronologico(self, request):
        """
        Reporte Cronológico - generates a report of the kardex records.
        parameters:
        - initialDate: YYYY-MM-DD
        - finalDate: YYYY-MM-DD
        - tipo_documento: 'EXCEL' or 'WORD'
        """
        initialDate = request.query_params.get("initialDate")
        finalDate = request.query_params.get("finalDate")
        tipo_documento = request.query_params.get("tipo_documento")
        service = NoContenciososReportService()
        if tipo_documento == 'EXCEL':
            response = service.generate_excel_report(desde=initialDate, hasta=finalDate)
        else:
            response = service.generate_word_report(desde=initialDate, hasta=finalDate)
        return response

    @action(detail=False, methods=["get"], url_path="garantias-cronologico")
    def garantias_cronologico(self, request):
        """
        Reporte Cronológico Garantias - generates a report of the kardex records.
        parameters:
        - initialDate: YYYY-MM-DD
        - finalDate: YYYY-MM-DD
        - tipo_documento: 'EXCEL' or 'WORD'
        """
        initialDate = request.query_params.get("initialDate")
        finalDate = request.query_params.get("finalDate")
        tipo_documento = request.query_params.get("tipo_documento")
        service = GarantiasReportService()
        if tipo_documento == 'EXCEL':
            response = service.generate_excel_report(desde=initialDate, hasta=finalDate)
        else:
            response = service.generate_word_report(desde=initialDate, hasta=finalDate)
        return response

    @action(detail=False, methods=["get"], url_path="testamentos-cronologico")
    def testamentos_cronologico(self, request):
        """
        Reporte Cronológico Testamentos - generates a report of the kardex records.
        parameters:
        - initialDate: YYYY-MM-DD
        - finalDate: YYYY-MM-DD
        - tipo_documento: 'EXCEL' or 'WORD'
        """
        initialDate = request.query_params.get("initialDate")
        finalDate = request.query_params.get("finalDate")
        tipo_documento = request.query_params.get("tipo_documento")

        service = TestamentosReportService()
        if tipo_documento == 'EXCEL':
            response = service.generate_excel_report(desde=initialDate, hasta=finalDate)
        else:
            response = service.generate_word_report(desde=initialDate, hasta=finalDate)
        return response

    @action(detail=False, methods=["get"], url_path="uif-errors")
    def uif_error_dashboard(self, request):
        """
        UIF Error Dashboard - validates kardex records for UIF compliance.
        EXACTLY like the old PHP script.
        """

        try:
            # Get and validate parameters
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")
            include_valid = request.query_params.get("includeValid", "false").lower() == "true"

            if not initial_date or not final_date:
                return Response(
                    {"error": "Both initialDate and finalDate are required (DD/MM/YYYY format)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Convert dates - support both DD/MM/YYYY and YYYY-MM-DD formats
            try:
                # Try DD/MM/YYYY format first (like PHP)
                start_date = datetime.strptime(initial_date, "%d/%m/%Y").date()
                end_date = datetime.strptime(final_date, "%d/%m/%Y").date()
            except ValueError:
                try:
                    # Try YYYY-MM-DD format as fallback
                    start_date = datetime.strptime(initial_date, "%Y-%m-%d").date()
                    end_date = datetime.strptime(final_date, "%Y-%m-%d").date()
                except ValueError:
                    return Response(
                        {"error": "Invalid date format. Use DD/MM/YYYY or YYYY-MM-DD"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # EXACTLY like PHP: Get kardex records for date range
            kardex_records = (
                models.Kardex.objects.filter(fechaescritura__range=[start_date, end_date])
                .exclude(idtipkar__in=[2, 5])  # Exclude types 2 and 5
                .order_by("-idkardex")
            )

            # OPTIMIZATION: Pre-fetch all Tiposdeacto data in a single query
            # Get all unique act codes from all kardex records
            all_act_codes = set()
            for kardex in kardex_records:
                if kardex.codactos:
                    for i in range(0, len(kardex.codactos), 3):
                        if i + 3 <= len(kardex.codactos):
                            all_act_codes.add(kardex.codactos[i : i + 3])

            # Single query to get all relevant Tiposdeacto records
            tipos_acto_map = {}
            if all_act_codes:
                tipos_acto_queryset = models.Tiposdeacto.objects.filter(
                    idtipoacto__in=list(all_act_codes), actouif__isnull=False
                ).exclude(actouif="")

                for tipo_acto in tipos_acto_queryset:
                    tipos_acto_map[tipo_acto.idtipoacto] = tipo_acto

            # OPTIMIZATION: Pre-fetch ALL related data to avoid N+1 queries
            # Get all unique kardex numbers
            kardex_numbers = [k.kardex for k in kardex_records]

            # Bulk fetch patrimonial data
            patrimonial_map = {}
            if kardex_numbers:
                patrimonial_queryset = models.Patrimonial.objects.filter(
                    kardex__in=kardex_numbers, idtipoacto__in=list(all_act_codes)
                )
                for patrimonial in patrimonial_queryset:
                    # Use tuple key format to match _get_patrimonial_summary method
                    key = (patrimonial.kardex, str(patrimonial.idtipoacto).zfill(3))
                    patrimonial_map[key] = patrimonial

            # Bulk fetch contratantes data
            contratantes_map = {}
            if kardex_numbers:
                contratantes_queryset = models.Contratantes.objects.filter(
                    kardex__in=kardex_numbers
                )
                for contratante in contratantes_queryset:
                    if contratante.kardex not in contratantes_map:
                        contratantes_map[contratante.kardex] = []
                    contratantes_map[contratante.kardex].append(contratante)

            # Get all contratante IDs and bulk fetch cliente2 data
            all_contratante_ids = []
            for contratantes in contratantes_map.values():
                all_contratante_ids.extend([c.idcontratante for c in contratantes])

            clientes_map = {}
            if all_contratante_ids:
                clientes_queryset = models.Cliente2.objects.filter(
                    idcontratante__in=all_contratante_ids
                )
                for cliente in clientes_queryset:
                    clientes_map[cliente.idcontratante] = cliente

            # Bulk fetch contratantesxacto data
            contratantesxacto_map = {}
            if all_contratante_ids and kardex_numbers and all_act_codes:
                contratantesxacto_queryset = models.Contratantesxacto.objects.filter(
                    kardex__in=kardex_numbers,
                    idtipoacto__in=list(all_act_codes),
                    idcontratante__in=all_contratante_ids,
                )
                for cxa in contratantesxacto_queryset:
                    key = f"{cxa.kardex}_{cxa.idtipoacto}_{cxa.idcontratante}"
                    contratantesxacto_map[key] = cxa

            # Process validation EXACTLY like PHP - separate into three categories like PHP script
            errors = []  # Lista de Errores
            valid_kardex_ro = []  # Lista de Kardex(RO) - valid records for UIF
            kardex_no_envian = []  # Lista de kardex que no envían

            error_summary = {
                "missing_uif_code": 0,
                "missing_escritura_number": 0,
                "missing_conclusion_date": 0,
                "missing_patrimonial_data": 0,
                "invalid_act_codes": 0,
                "currency_without_amount": 0,
                "amount_mismatch": 0,
                "missing_participant_amount": 0,
            }

            for kardex in kardex_records:
                # EXACTLY like PHP: Parse codactos (3-character codes)
                if not kardex.codactos:
                    continue

                act_codes = []
                for i in range(0, len(kardex.codactos), 3):
                    if i + 3 <= len(kardex.codactos):
                        act_codes.append(kardex.codactos[i : i + 3])

                # EXACTLY like PHP: Validate each act code
                for act_code in act_codes:
                    # OPTIMIZATION: Use pre-fetched data instead of database query
                    tipo_acto = tipos_acto_map.get(act_code)

                    # Build record data EXACTLY like PHP
                    record_data = {
                        "idkardex": kardex.idkardex,
                        "kardex": kardex.kardex,
                        "idtipkar": kardex.idtipkar,
                        "tipo_instrumento": self._get_tipo_instrumento(kardex.idtipkar),
                        "codacto": act_code,
                        "numescritura": kardex.numescritura,
                        "fechaescritura": kardex.fechaescritura,
                        "fechaconclusion": kardex.fechaconclusion,
                        "tipo": "I",  # Initial record
                    }

                    if tipo_acto:
                        # EXACTLY like PHP: Valid record goes to 'ro' table equivalent
                        record_data.update(
                            {
                                "act": tipo_acto.desacto,
                                "uif_code": tipo_acto.actouif,
                                "umbral": tipo_acto.umbral,
                                "status": "valid",
                                "validation_errors": [],
                            }
                        )

                        # EXACTLY like PHP: Check patrimonial data and amounts
                        patrimonial_errors = self._validate_patrimonial_data(
                            kardex.kardex,
                            act_code,
                            tipo_acto.desacto,
                            patrimonial_map,
                            contratantes_map,
                            clientes_map,
                            contratantesxacto_map,
                        )

                        if patrimonial_errors:
                            # If there are patrimonial errors, add to errors list
                            errors.extend(patrimonial_errors)
                            for error in patrimonial_errors:
                                if error["error_type"] == "currency_without_amount":
                                    error_summary["currency_without_amount"] += 1
                                elif error["error_type"] == "amount_mismatch":
                                    error_summary["amount_mismatch"] += 1
                                elif error["error_type"] == "missing_participant_amount":
                                    error_summary["missing_participant_amount"] += 1

                            # Don't add patrimonial errors to kardex_no_envian
                            # They belong in lista_errores only
                        else:
                            # No patrimonial errors - this is a valid record for UIF (RO)
                            # Add patrimonial data like PHP script
                            patrimonial_data = self._get_patrimonial_summary(
                                kardex.kardex, act_code, patrimonial_map
                            )
                            record_data.update(patrimonial_data)
                            valid_kardex_ro.append(record_data)

                        if include_valid:
                            # For backward compatibility
                            pass
                    else:
                        # EXACTLY like PHP: Invalid record goes to 'ro_not' table equivalent
                        record_data.update(
                            {
                                "act": f"Acto {act_code}",
                                "uif_code": "",
                                "status": "invalid",
                                "error_type": "missing_uif_code",
                                "error_description": f"Código UIF faltante para el acto {act_code}",
                            }
                        )
                        errors.append(record_data)
                        error_summary["missing_uif_code"] += 1

                        # Don't add validation errors to kardex_no_envian
                        # They belong in lista_errores only

                # EXACTLY like PHP: Check for missing escritura number
                if not kardex.numescritura or kardex.numescritura.strip() == "":
                    # Get act description from tipo_acto if available
                    act_desc = tipo_acto.desacto if tipo_acto else f"Acto {act_code}"
                    escritura_error = {
                        "idkardex": kardex.idkardex,
                        "kardex": kardex.kardex,
                        "act": act_desc,  # Add act description
                        "status": "invalid",
                        "error_type": "missing_escritura_number",
                        "error_description": "Número de escritura faltante",
                    }
                    errors.append(escritura_error)
                    error_summary["missing_escritura_number"] += 1

                    # Don't add validation errors to kardex_no_envian
                    # They belong in lista_errores only

                # EXACTLY like PHP: Check for missing conclusion date
                if not kardex.fechaconclusion:
                    # Get act description from tipo_acto if available
                    act_desc = tipo_acto.desacto if tipo_acto else f"Acto {act_code}"
                    conclusion_error = {
                        "idkardex": kardex.idkardex,
                        "kardex": kardex.kardex,
                        "act": act_desc,  # Add act description
                        "status": "invalid",
                        "error_type": "missing_conclusion_date",
                        "error_description": "Fecha de conclusión faltante",
                    }
                    errors.append(conclusion_error)
                    error_summary["missing_conclusion_date"] += 1

                    # Don't add validation errors to kardex_no_envian
                    # They belong in lista_errores only

            # EXACTLY like PHP: Process complementary data (contract signing dates)
            complementary_errors = self._process_complementary_data(start_date, end_date)
            errors.extend(complementary_errors)

            # EXACTLY like PHP: Get additional "no envían" records from separate source
            # This replicates the PHP script's separate query to ro_not table
            additional_no_envian = self._get_additional_no_envian_records(start_date, end_date)
            kardex_no_envian.extend(additional_no_envian)

            # Get filter type parameter to determine which category to paginate
            filter_type = request.query_params.get("type", "errors")  # errors, ro, no_envian

            # Determine which data to paginate based on type parameter
            if filter_type == "ro":
                paginated_data = self.paginate_queryset(valid_kardex_ro)
                data_key = "lista_kardex_ro"
            elif filter_type == "no_envian":
                paginated_data = self.paginate_queryset(kardex_no_envian)
                data_key = "lista_kardex_no_envian"
            else:  # Default to errors
                paginated_data = self.paginate_queryset(errors)
                data_key = "lista_errores"

            # Build response with all three categories like PHP script
            response_data = {
                "lista_errores": errors if filter_type != "errors" else paginated_data,
                "lista_kardex_ro": valid_kardex_ro if filter_type != "ro" else paginated_data,
                "lista_kardex_no_envian": (
                    kardex_no_envian if filter_type != "no_envian" else paginated_data
                ),
                "summary": {
                    "total_kardex": len(kardex_records),
                    "total_errors": len(errors),
                    "total_valid_ro": len(valid_kardex_ro),
                    "total_no_envian": len(kardex_no_envian),
                    "error_breakdown": error_summary,
                    "date_range": {
                        "start": initial_date,
                        "end": final_date,
                        "start_iso": start_date.isoformat(),
                        "end_iso": end_date.isoformat(),
                        "start_formatted": start_date.strftime("%d/%m/%Y"),
                        "end_formatted": end_date.strftime("%d/%m/%Y"),
                    },
                },
                "metadata": {
                    "processed_at": timezone.now().isoformat(),
                    "include_valid_records": include_valid,
                    "current_filter": filter_type,
                    "paginated_category": data_key,
                },
            }

            if include_valid:
                # For backward compatibility
                response_data["valid_records"] = valid_kardex_ro
                response_data["summary"]["total_valid"] = len(valid_kardex_ro)

            return self.get_paginated_response(response_data)

        except Exception as e:
            logger.error(f"Error in UIF error dashboard: {str(e)}", exc_info=True)
            return Response(
                {
                    "error": "Internal server error while processing UIF validation",
                    "detail": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _get_tipo_instrumento(self, idtipkar):
        """EXACTLY like PHP: Get instrument type abbreviation based on idtipkar."""
        tipo_map = {
            1: "E",  # Escritura
            3: "T",  # Transferencia
            4: "G",  # Otros
        }
        return tipo_map.get(idtipkar, "SIN INICIAL")

    def _process_complementary_data(self, start_date, end_date):
        """EXACTLY like PHP: Process complementary data for contracts signed in date range."""
        complementary_errors = []

        # EXACTLY like PHP: Get contracts signed in date range but with earlier escritura dates
        # This replicates the complex query from the original PHP script
        contratantes = models.Contratantes.objects.filter(
            fechafirma__isnull=False, fechafirma__range=[start_date, end_date]
        )

        for contratante in contratantes:
            if not contratante.kardex:
                continue

            # EXACTLY like PHP: Check if kardex exists and meets criteria
            try:
                kardex = models.Kardex.objects.get(kardex=contratante.kardex)

                # EXACTLY like PHP: Same conditions as original script
                if (
                    kardex.fechaescritura
                    and kardex.fechaescritura < start_date
                    and kardex.idtipkar not in [2, 5]
                ):

                    # This is complementary data that should be in 'ro' table
                    # but we're treating it as potential error for now
                    complementary_errors.append(
                        {
                            "idkardex": kardex.idkardex,
                            "kardex": kardex.kardex,
                            "status": "complementary",
                            "error_type": "complementary_data",
                            "error_description": "Contract signed in date range but escritura from earlier period",
                            "fecha_firma": contratante.fechafirma,
                            "fecha_escritura": kardex.fechaescritura,
                        }
                    )
            except models.Kardex.DoesNotExist:
                continue

        return complementary_errors

    def _validate_patrimonial_data(
        self,
        kardex,
        act_code,
        act_description,
        patrimonial_map,
        contratantes_map,
        clientes_map,
        contratantesxacto_map,
    ):
        """
        EXACTLY like PHP: Validate patrimonial data, amounts, and currency codes.
        This replicates the complex validation logic from the original PHP script.
        Uses pre-fetched data to avoid N+1 queries.
        """
        patrimonial_errors = []

        try:
            # Get patrimonial data from pre-fetched map
            patrimonial_key = f"{kardex}_{act_code}"
            patrimonial = patrimonial_map.get(patrimonial_key)

            if not patrimonial:
                return patrimonial_errors

            # Get all contratantes for this kardex from pre-fetched map
            contratantes = contratantes_map.get(kardex, [])

            # Check if currency code is provided without amounts
            if patrimonial.idmon and patrimonial.idmon != "":
                if not patrimonial.importetrans or patrimonial.importetrans == 0:
                    # Currency code without amount - this is an error
                    for contratante in contratantes:
                        cliente = clientes_map.get(contratante.idcontratante)
                        if cliente:
                            nombre = (
                                cliente.nombre
                                or cliente.razonsocial
                                or f"Contratante {contratante.idcontratante}"
                            )

                            patrimonial_errors.append(
                                {
                                    "idkardex": patrimonial.kardex,
                                    "kardex": kardex,
                                    "act": act_description,
                                    "status": "invalid",
                                    "error_type": "currency_without_amount",
                                    "error_description": f"{nombre}, código de moneda no se debe informar sin montos",
                                }
                            )

            # Check for amount mismatches and missing participant amounts
            if patrimonial.importetrans and patrimonial.importetrans > 0:
                # Get all contratantes with amounts
                contratantes_with_amounts = []
                total_contratante_amounts = 0

                for contratante in contratantes:
                    cliente = clientes_map.get(contratante.idcontratante)
                    if not cliente:
                        continue

                    nombre = (
                        cliente.nombre
                        or cliente.razonsocial
                        or f"Contratante {contratante.idcontratante}"
                    )

                    # Check if contratante has amount in Contratantesxacto using pre-fetched data
                    contratante_acto_key = f"{kardex}_{act_code}_{contratante.idcontratante}"
                    contratante_acto = contratantesxacto_map.get(contratante_acto_key)

                    if contratante_acto and contratante_acto.monto:
                        try:
                            monto = float(contratante_acto.monto)
                            total_contratante_amounts += monto
                            contratantes_with_amounts.append({"nombre": nombre, "monto": monto})
                        except (ValueError, TypeError):
                            pass
                    else:
                        # Missing amount for participant
                        patrimonial_errors.append(
                            {
                                "idkardex": patrimonial.kardex,
                                "kardex": kardex,
                                "act": act_description,
                                "status": "invalid",
                                "error_type": "missing_participant_amount",
                                "error_description": f"{nombre} Monto por Participante",
                            }
                        )

                # Check if total amounts match
                if total_contratante_amounts > 0:
                    patrimonial_total = float(patrimonial.importetrans)

                    if (
                        abs(total_contratante_amounts - patrimonial_total) > 0.01
                    ):  # Allow small rounding differences
                        if total_contratante_amounts > patrimonial_total:
                            patrimonial_errors.append(
                                {
                                    "idkardex": patrimonial.kardex,
                                    "kardex": kardex,
                                    "act": act_description,
                                    "status": "invalid",
                                    "error_type": "amount_mismatch",
                                    "error_description": f"La suma de los montos de los contratantes otorgantes supera el monto total de la operacion: {patrimonial_total:.2f}",
                                }
                            )
                        else:
                            patrimonial_errors.append(
                                {
                                    "idkardex": patrimonial.kardex,
                                    "kardex": kardex,
                                    "act": act_description,
                                    "status": "invalid",
                                    "error_type": "amount_mismatch",
                                    "error_description": f"La suma de los montos de los contratantes beneficierios supera el monto total de la operacion: {patrimonial_total:.2f}",
                                }
                            )

        except Exception as e:
            # Log any errors in validation but don't break the process
            logger.warning(f"Error validating patrimonial data for kardex {kardex}: {str(e)}")

        return patrimonial_errors

    def _get_patrimonial_summary(self, kardex_number, act_code, patrimonial_map):
        """
        Get patrimonial summary data for a valid RO record.
        This method enriches the record with patrimonial information like the PHP script.
        """
        try:
            # Get patrimonial data from the pre-fetched map
            patrimonial_key = (kardex_number, act_code)
            patrimonial = patrimonial_map.get(patrimonial_key)

            if not patrimonial:
                # Return default values if no patrimonial data found
                return {
                    "tipo_moneda": "SOLES",
                    "tipo_cambio": 0.0,
                    "patrimonial": 0.0,
                    "en_dolares": 0.0,
                    "currency_symbol": "S./ ",
                }

            # Determine currency type and symbol
            if patrimonial.idmon == 2:  # Dollars
                currency_symbol = "$ "
                currency_description = "DOLARES"
            else:  # Soles
                currency_symbol = "S./ "
                currency_description = "SOLES"

            # Calculate amount in dollars
            tipo_cambio = float(patrimonial.tipocambio) if patrimonial.tipocambio else 1.0
            importe_trans = float(patrimonial.importetrans) if patrimonial.importetrans else 0.0

            if patrimonial.idmon == 1:  # Soles - convert to dollars
                en_dolares = importe_trans / tipo_cambio if tipo_cambio > 0 else 0.0
            else:  # Already in dollars
                en_dolares = importe_trans

            return {
                "tipo_moneda": currency_description,
                "tipo_cambio": tipo_cambio,
                "patrimonial": importe_trans,
                "en_dolares": round(en_dolares, 2),
                "currency_symbol": currency_symbol,
            }

        except Exception as e:
            logger.warning(
                f"Error getting patrimonial summary for kardex {kardex_number}: {str(e)}"
            )
            # Return default values on error
            return {
                "tipo_moneda": "SOLES",
                "tipo_cambio": 0.0,
                "patrimonial": 0.0,
                "en_dolares": 0.0,
                "currency_symbol": "S./ ",
            }

    def _get_additional_no_envian_records(self, start_date, end_date):
        """
        Get additional records that "no envían" to UIF.
        This replicates the PHP script's separate query to ro_not table.

        These are records that are NOT part of the main UIF validation process
        but should be included in the "Lista de kardex que no envían".
        """
        try:
            # Get records that are in the date range but NOT in the main kardex validation
            # This includes records that might be:
            # - Below threshold amounts
            # - Different types of acts not requiring UIF submission
            # - Records in a different status

            # Query for records that have patrimonial data but don't meet UIF criteria
            additional_records = []

            # Get all kardex records in the date range that might be excluded from UIF
            excluded_kardex = (
                models.Kardex.objects.filter(fechaescritura__range=[start_date, end_date])
                .exclude(
                    # Exclude records that are already processed in main validation
                    codactos__isnull=True
                )
                .exclude(
                    # Exclude records that are clearly for UIF (have UIF codes)
                    codactos__regex=r"[0-9]{3}.*[0-9]{3}"  # Has multiple act codes
                )
            )

            for kardex in excluded_kardex:
                # Parse act codes if they exist
                if kardex.codactos:
                    act_codes = []
                    for i in range(0, len(kardex.codactos), 3):
                        if i + 3 <= len(kardex.codactos):
                            act_codes.append(kardex.codactos[i : i + 3])

                    for act_code in act_codes:
                        # Get act description
                        tipo_acto = models.Tiposdeacto.objects.filter(idtipoacto=act_code).first()

                        act_description = tipo_acto.desacto if tipo_acto else f"Acto {act_code}"

                        # Get patrimonial data
                        patrimonial = models.Patrimonial.objects.filter(
                            kardex=kardex.kardex, idtipoacto=act_code
                        ).first()

                        if patrimonial:
                            # Determine currency type
                            if patrimonial.idmon == 2:  # Dollars
                                currency_description = "DOLARES"
                            else:  # Soles
                                currency_description = "SOLES"

                            # Build record data like PHP script
                            record_data = {
                                "idkardex": kardex.idkardex,
                                "kardex": kardex.kardex,
                                "act": act_description,
                                "tipo_moneda": currency_description,
                                "patrimonial": (
                                    float(patrimonial.importetrans)
                                    if patrimonial.importetrans
                                    else 0.0
                                ),
                                "status": "excluded_from_uif",
                                "reason": "Below threshold or not requiring UIF submission",
                            }

                            additional_records.append(record_data)
                        else:
                            # Record without patrimonial data
                            record_data = {
                                "idkardex": kardex.idkardex,
                                "kardex": kardex.kardex,
                                "act": act_description,
                                "tipo_moneda": "SOLES",
                                "patrimonial": 0.0,
                                "status": "excluded_from_uif",
                                "reason": "No patrimonial data",
                            }

                            additional_records.append(record_data)

            return additional_records

        except Exception as e:
            logger.warning(f"Error getting additional no envían records: {str(e)}")
            return []

    @action(detail=False, methods=["get"], url_path="uif-report-excel")
    def uif_report_excel(self, request):
        """Generate Excel file for UIF report."""
        try:
            # Get and validate parameters
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")

            if not initial_date or not final_date:
                return Response(
                    {"error": "Both initialDate and finalDate are required (DD/MM/YYYY format)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get UIF data by calling the internal method directly
            try:
                # Convert dates - support both DD/MM/YYYY and YYYY-MM-DD formats
                try:
                    # Try DD/MM/YYYY format first (like PHP)
                    start_date = datetime.strptime(initial_date, "%d/%m/%Y").date()
                    end_date = datetime.strptime(final_date, "%d/%m/%Y").date()
                except ValueError:
                    try:
                        # Try YYYY-MM-DD format as fallback
                        start_date = datetime.strptime(initial_date, "%Y-%m-%d").date()
                        end_date = datetime.strptime(final_date, "%Y-%m-%d").date()
                    except ValueError:
                        return Response(
                            {"error": "Invalid date format. Use DD/MM/YYYY or YYYY-MM-DD"},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                # Get kardex records for date range
                kardex_records = (
                    models.Kardex.objects.filter(fechaescritura__range=[start_date, end_date])
                    .exclude(idtipkar__in=[2, 5])  # Exclude types 2 and 5
                    .order_by("-idkardex")
                )

                # Process records using the dashboard logic
                valid_kardex_ro = []
                errors = []
                kardex_no_envian = []
                error_summary = {
                    "missing_uif_code": 0,
                    "missing_escritura_number": 0,
                    "missing_conclusion_date": 0,
                    "missing_patrimonial_data": 0,
                    "invalid_act_codes": 0,
                    "currency_without_amount": 0,
                    "amount_mismatch": 0,
                    "missing_participant_amount": 0,
                }

                # Process each kardex record
                for kardex in kardex_records:
                    # Get act codes
                    if kardex.codactos:
                        act_codes = [
                            kardex.codactos[i : i + 3] for i in range(0, len(kardex.codactos), 3)
                        ]

                        # Process each act code
                        for act_code in act_codes:
                            # Get tipo_acto
                            tipo_acto = (
                                models.Tiposdeacto.objects.filter(
                                    idtipoacto=act_code, actouif__isnull=False
                                )
                                .exclude(actouif="")
                                .first()
                            )

                            if tipo_acto:
                                # Valid record - add to RO list
                                valid_record = {
                                    "idkardex": kardex.idkardex,
                                    "kardex": kardex.kardex,
                                    "idtipkar": kardex.idtipkar,
                                    "codacto": act_code,
                                    "numescritura": kardex.numescritura,
                                    "fechaescritura": kardex.fechaescritura,
                                    "fechaconclusion": kardex.fechaconclusion,
                                    "act": tipo_acto.desacto,
                                    "uif_code": tipo_acto.actouif,
                                    "umbral": tipo_acto.umbral,
                                    "status": "valid",
                                }
                                valid_kardex_ro.append(valid_record)

                data = {
                    "lista_errores": errors,
                    "lista_kardex_ro": valid_kardex_ro,
                    "lista_kardex_no_envian": kardex_no_envian,
                    "summary": {
                        "total_kardex": len(kardex_records),
                        "total_errors": len(errors),
                        "total_valid_ro": len(valid_kardex_ro),
                        "total_no_envian": len(kardex_no_envian),
                        "error_breakdown": error_summary,
                        "date_range": {
                            "start": initial_date,
                            "end": final_date,
                            "start_iso": start_date.isoformat(),
                            "end_iso": end_date.isoformat(),
                        },
                    },
                }
            except Exception as e:
                logger.error(f"Error processing UIF data: {str(e)}", exc_info=True)
                return Response(
                    {"error": "Error processing UIF data", "detail": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Generate Excel file
            report_service = UifReportService()
            return report_service.generate_excel_report(data, initial_date, final_date)
        except Exception as e:
            logger.error(f"Error generating UIF report Excel: {str(e)}", exc_info=True)
            return Response(
                {"error": "Error generating UIF report Excel", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="uif-report-plane")
    def uif_report_plane(self, request):
        """
        Generate plane text file for UIF report.

        Query Parameters:
        - initialDate: Start date (DD/MM/YYYY)
        - finalDate: End date (DD/MM/YYYY)
        """
        try:
            # Get and validate parameters
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")

            if not initial_date or not final_date:
                return Response(
                    {"error": "Both initialDate and finalDate are required (DD/MM/YYYY format)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Convert dates - support both DD/MM/YYYY and YYYY-MM-DD formats
            try:
                # Try DD/MM/YYYY format first (like PHP)
                start_date = datetime.strptime(initial_date, "%d/%m/%Y").date()
                end_date = datetime.strptime(final_date, "%d/%m/%Y").date()
            except ValueError:
                try:
                    # Try YYYY-MM-DD format as fallback
                    start_date = datetime.strptime(initial_date, "%Y-%m-%d").date()
                    end_date = datetime.strptime(final_date, "%Y-%m-%d").date()
                except ValueError:
                    return Response(
                        {"error": "Invalid date format. Use DD/MM/YYYY or YYYY-MM-DD"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Get UIF data by calling the internal method directly
            try:
                # Get kardex records for date range
                kardex_records = (
                    models.Kardex.objects.filter(fechaescritura__range=[start_date, end_date])
                    .exclude(idtipkar__in=[2, 5])  # Exclude types 2 and 5
                    .order_by("-idkardex")
                )

                # Process records using the dashboard logic
                valid_kardex_ro = []
                errors = []
                kardex_no_envian = []
                error_summary = {
                    "missing_uif_code": 0,
                    "missing_escritura_number": 0,
                    "missing_conclusion_date": 0,
                    "missing_patrimonial_data": 0,
                    "invalid_act_codes": 0,
                    "currency_without_amount": 0,
                    "amount_mismatch": 0,
                    "missing_participant_amount": 0,
                }

                data = {
                    "lista_errores": errors,
                    "lista_kardex_ro": valid_kardex_ro,
                    "lista_kardex_no_envian": kardex_no_envian,
                    "summary": {
                        "total_kardex": len(kardex_records),
                        "total_errors": len(errors),
                        "total_valid_ro": len(valid_kardex_ro),
                        "total_no_envian": len(kardex_no_envian),
                        "error_breakdown": error_summary,
                        "date_range": {
                            "start": initial_date,
                            "end": final_date,
                            "start_iso": start_date.isoformat(),
                            "end_iso": end_date.isoformat(),
                        },
                    },
                }

                # Generate plane report using the service
                report_service = UifReportService()
                response = report_service.generate_plane_report(data, initial_date, final_date)

                # Extract filename from Content-Disposition header
                content_disposition = response.get("Content-Disposition", "")
                filename = "uif_report.txt"  # fallback
                if "filename=" in content_disposition:
                    filename = content_disposition.split("filename=")[1].replace('"', "")

                # Return JSON response with filename and file content
                import base64

                file_content = response.content.decode("utf-8")
                file_content_b64 = base64.b64encode(response.content).decode("utf-8")

                return Response(
                    {
                        "filename": filename,
                        "content": file_content_b64,
                        "content_type": "text/plain",
                    }
                )

            except Exception as e:
                logger.error(f"Error processing UIF data: {str(e)}", exc_info=True)
                return Response(
                    {"error": "Error processing UIF data", "detail": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as e:
            logger.error(f"Error generating UIF report plane: {str(e)}", exc_info=True)
            return Response(
                {"error": "Error generating UIF report plane", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="pdt-escrituras")
    def pdt_errors(self, request):
        """
        Get PDT validation errors for escrituras in a date range.

        Query Parameters:
        - initialDate: Start date (DD/MM/YYYY)
        - finalDate: End date (DD/MM/YYYY)
        """
        try:
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")

            if not initial_date or not final_date:
                return Response(
                    {"error": 1, "errorDescription": "Se requieren las fechas inicial y final"},
                    status=400,
                )

            # Initialize PDT service
            pdt_service = PdtEscriturasService(initial_date, final_date)
            pdt_service.load_data()
            results = pdt_service.get_results()

            # Get paginated results
            page = self.paginate_queryset(results["list"])
            if page is not None:
                return self.get_paginated_response(
                    {
                        "list": page,
                        "totalError": results["totalError"],
                        "totalRecords": results["totalRecords"],
                        "summary": results["summary"],
                    }
                )

            return Response(results)

        except Exception as e:
            return Response({"error": 1, "errorDescription": str(e)}, status=500)

    @action(detail=False, methods=["get"], url_path="pdt-vehiculares")
    def pdt_vehiculares(self, request):
        """
        Get PDT validation errors for vehicular acts in a date range.

        Query Parameters:
        - initialDate: Start date (DD/MM/YYYY)
        - finalDate: End date (DD/MM/YYYY)
        """
        try:
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")

            if not initial_date or not final_date:
                return Response(
                    {"error": 1, "errorDescription": "Se requieren las fechas inicial y final"},
                    status=400,
                )

            # Initialize PDT service
            pdt_service = PdtVehicularesService(initial_date, final_date)
            pdt_service.load_data()
            results = pdt_service.get_results()

            # Get paginated results
            page = self.paginate_queryset(results["list"])
            if page is not None:
                return self.get_paginated_response(
                    {
                        "list": page,
                        "totalError": results["totalError"],
                        "totalRecords": results["totalRecords"],
                        "summary": results["summary"],
                    }
                )

            return Response(results)

        except Exception as e:
            return Response({"error": 1, "errorDescription": str(e)}, status=500)

    @action(detail=False, methods=["get"], url_path="pdt-garantias")
    def pdt_garantias(self, request):
        """
        Get PDT validation errors for garantías in a date range.

        Query Parameters:
        - initialDate: Start date (DD/MM/YYYY)
        - finalDate: End date (DD/MM/YYYY)
        """
        try:
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")

            if not initial_date or not final_date:
                return Response(
                    {"error": 1, "errorDescription": "Se requieren las fechas inicial y final"},
                    status=400,
                )

            # Initialize PDT service
            pdt_service = PdtGarantiasService(initial_date, final_date)
            pdt_service.load_data()
            results = pdt_service.get_results()

            # Get paginated results
            page = self.paginate_queryset(results["list"])
            if page is not None:
                return self.get_paginated_response(
                    {
                        "list": page,
                        "totalError": results["totalError"],
                        "totalRecords": results["totalRecords"],
                        "summary": results["summary"],
                    }
                )

            return Response(results)

        except Exception as e:
            return Response({"error": 1, "errorDescription": str(e)}, status=500)

    @action(detail=False, methods=["post"])
    def calculate(self, request):
        """
        Calculate and distribute percentages evenly among participants.
        Based on PHP script logic for percentage calculation.
        PERFORMS ACTUAL DATABASE UPDATES.
        """
        try:
            kardex = request.data.get("kardex")
            item = request.data.get("item")  # Get item from client

            if not kardex:
                return Response({"error": 1, "errorDescription": "Kardex is required"}, status=400)

            if not item:
                return Response({"error": 1, "errorDescription": "Item is required"}, status=400)

            # Get current date for modification
            fecha_modificacion = datetime.now().strftime("%d/%m/%Y")

            # Get detalle_actos_kardex records for this kardex using ORM
            detalle_actos = models.DetalleActosKardex.objects.filter(kardex=kardex)

            if not detalle_actos.exists():
                return Response(
                    {"error": 1, "errorDescription": "No se encontraron actos para este kardex"},
                    status=404,
                )

            results = []
            updates_performed = {
                "patrimonial_updates": 0,
                "contratantesxacto_condition_updates": 0,
                "contratantesxacto_percentage_updates": 0,
                "kardex_updates": 0,
            }

            with transaction.atomic():  # Ensure all updates succeed or fail together

                for detalle_acto in detalle_actos:
                    item_val = item  # Use item from client
                    kardex_val = detalle_acto.kardex
                    idtipoacto = detalle_acto.idtipoacto

                    # 1. Update patrimonial table - set item field
                    patrimonial_updated = models.Patrimonial.objects.filter(
                        kardex=kardex_val, idtipoacto=idtipoacto
                    ).update(item=item_val)
                    updates_performed["patrimonial_updates"] += patrimonial_updated

                    # 2. Update contratantesxacto conditions from actocondicion
                    acto_condiciones = models.Actocondicion.objects.filter(idtipoacto=idtipoacto)

                    for condicion in acto_condiciones:
                        contratantes_updated = models.Contratantesxacto.objects.filter(
                            idcondicion=condicion.idcondicion,
                            kardex=kardex_val,
                            idtipoacto=idtipoacto,
                        ).update(
                            parte=condicion.parte,
                            uif=condicion.uif,
                            formulario=_condicion.formulario,
                            montop=condicion.montop or "",
                        )
                        updates_performed[
                            "contratantesxacto_condition_updates"
                        ] += contratantes_updated

                    # 3. Calculate and update percentages and amounts
                    # Get participants by parte (1 = vendedor/otorgante, 2 = comprador/beneficiario)
                    vendedores = models.Contratantesxacto.objects.filter(
                        kardex=kardex_val, parte="1"
                    )
                    numero_vendedores = vendedores.count()

                    compradores = models.Contratantesxacto.objects.filter(
                        kardex=kardex_val, parte="2"
                    )
                    numero_compradores = compradores.count()

                    # Get transaction amount
                    try:
                        patrimonial = models.Patrimonial.objects.get(
                            idtipoacto=idtipoacto, item=item_val
                        )
                        importe_trans = (
                            float(patrimonial.importetrans) if patrimonial.importetrans else 0
                        )
                    except models.Patrimonial.DoesNotExist:
                        importe_trans = 0

                    # Calculate percentage and amount distributions
                    vendedor_percentages = self._divide_evenly(numero_vendedores, 100)
                    comprador_percentages = self._divide_evenly(numero_compradores, 100)
                    vendedor_amounts = self._divide_evenly(numero_vendedores, importe_trans)
                    comprador_amounts = self._divide_evenly(numero_compradores, importe_trans)

                    # Update vendedores percentages and amounts
                    for i, vendedor in enumerate(vendedores):
                        percentage = vendedor_percentages[i] if i < len(vendedor_percentages) else 0
                        amount = vendedor_amounts[i] if i < len(vendedor_amounts) else 0

                        # Match PHP logic: WHERE item='$itemdiv' and parte = '1' and idcontratante=... and idtipoacto=...
                        updated_count = models.Contratantesxacto.objects.filter(
                            item=item_val,
                            parte="1",
                            idcontratante=vendedor.idcontratante,
                            idtipoacto=vendedor.idtipoacto,
                        ).update(porcentaje=str(percentage), monto=str(amount))
                        updates_performed["contratantesxacto_percentage_updates"] += updated_count

                    # Update compradores percentages and amounts
                    for i, comprador in enumerate(compradores):
                        percentage = (
                            comprador_percentages[i] if i < len(comprador_percentages) else 0
                        )
                        amount = comprador_amounts[i] if i < len(comprador_amounts) else 0

                        # Match PHP logic: WHERE item='$itemdiv' and parte = '2' and idcontratante=... and idtipoacto=...
                        updated_count = models.Contratantesxacto.objects.filter(
                            item=item_val,
                            parte="2",
                            idcontratante=comprador.idcontratante,
                            idtipoacto=comprador.idtipoacto,
                        ).update(porcentaje=str(percentage), monto=str(amount))
                        updates_performed["contratantesxacto_percentage_updates"] += updated_count

                    # Get participant names for display
                    participant_details = []

                    # Process vendedores
                    for i, vendedor in enumerate(vendedores):
                        try:
                            cliente = models.Cliente2.objects.get(
                                idcontratante=vendedor.idcontratante
                            )
                            if cliente.tipper == "N":  # Natural person
                                name = f"{cliente.prinom or ''} {cliente.segnom or ''} {cliente.apepat or ''} {cliente.apemat or ''}".strip()
                            else:  # Juridical person
                                name = cliente.razonsocial or ""

                            participant_details.append(
                                {
                                    "idcontratante": vendedor.idcontratante,
                                    "name": name.upper(),
                                    "type": "VENDEDOR/OTORGANTE",
                                    "parte": "1",
                                    "gets_percentage": True,
                                    "percentage": (
                                        vendedor_percentages[i]
                                        if i < len(vendedor_percentages)
                                        else 0
                                    ),
                                    "amount": (
                                        vendedor_amounts[i] if i < len(vendedor_amounts) else 0
                                    ),
                                }
                            )
                        except models.Cliente2.DoesNotExist:
                            participant_details.append(
                                {
                                    "idcontratante": vendedor.idcontratante,
                                    "name": "CLIENTE NO ENCONTRADO",
                                    "type": "VENDEDOR/OTORGANTE",
                                    "parte": "1",
                                    "gets_percentage": True,
                                    "percentage": (
                                        vendedor_percentages[i]
                                        if i < len(vendedor_percentages)
                                        else 0
                                    ),
                                    "amount": (
                                        vendedor_amounts[i] if i < len(vendedor_amounts) else 0
                                    ),
                                }
                            )

                    # Process compradores
                    for i, comprador in enumerate(compradores):
                        try:
                            cliente = models.Cliente2.objects.get(
                                idcontratante=comprador.idcontratante
                            )
                            if cliente.tipper == "N":  # Natural person
                                name = f"{cliente.prinom or ''} {cliente.segnom or ''} {cliente.apepat or ''} {cliente.apemat or ''}".strip()
                            else:  # Juridical person
                                name = cliente.razonsocial or ""

                            participant_details.append(
                                {
                                    "idcontratante": comprador.idcontratante,
                                    "name": name.upper(),
                                    "type": "COMPRADOR/BENEFICIARIO",
                                    "parte": "2",
                                    "gets_percentage": True,
                                    "percentage": (
                                        comprador_percentages[i]
                                        if i < len(comprador_percentages)
                                        else 0
                                    ),
                                    "amount": (
                                        comprador_amounts[i] if i < len(comprador_amounts) else 0
                                    ),
                                }
                            )
                        except models.Cliente2.DoesNotExist:
                            participant_details.append(
                                {
                                    "idcontratante": comprador.idcontratante,
                                    "name": "CLIENTE NO ENCONTRADO",
                                    "type": "COMPRADOR/BENEFICIARIO",
                                    "parte": "2",
                                    "gets_percentage": True,
                                    "percentage": (
                                        comprador_percentages[i]
                                        if i < len(comprador_percentages)
                                        else 0
                                    ),
                                    "amount": (
                                        comprador_amounts[i] if i < len(comprador_amounts) else 0
                                    ),
                                }
                            )

                    # Get other participants (representantes, etc.) who don't get percentages
                    otros_participantes = models.Contratantesxacto.objects.filter(
                        kardex=kardex_val
                    ).exclude(parte__in=["1", "2"])

                    for participante in otros_participantes:
                        try:
                            cliente = models.Cliente2.objects.get(
                                idcontratante=participante.idcontratante
                            )
                            if cliente.tipper == "N":  # Natural person
                                name = f"{cliente.prinom or ''} {cliente.segnom or ''} {cliente.apepat or ''} {cliente.apemat or ''}".strip()
                            else:  # Juridical person
                                name = cliente.razonsocial or ""

                            participant_details.append(
                                {
                                    "idcontratante": participante.idcontratante,
                                    "name": name.upper(),
                                    "type": f"PARTE_{participante.parte}",
                                    "parte": participante.parte,
                                    "gets_percentage": False,
                                    "percentage": 0,
                                    "amount": 0,
                                    "reason": "No recibe porcentaje según configuración de acto",
                                }
                            )
                        except models.Cliente2.DoesNotExist:
                            participant_details.append(
                                {
                                    "idcontratante": participante.idcontratante,
                                    "name": "CLIENTE NO ENCONTRADO",
                                    "type": f"PARTE_{participante.parte}",
                                    "parte": participante.parte,
                                    "gets_percentage": False,
                                    "percentage": 0,
                                    "amount": 0,
                                    "reason": "No recibe porcentaje según configuración de acto",
                                }
                            )

                    results.append(
                        {
                            "item": item_val,
                            "idtipoacto": idtipoacto,
                            "importe_trans": importe_trans,
                            "numero_vendedores": numero_vendedores,
                            "numero_compradores": numero_compradores,
                            "participants": participant_details,
                        }
                    )

                # 4. Update kardex modification date
                kardex_updated = models.Kardex.objects.filter(kardex=kardex).update(
                    fecha_modificacion=fecha_modificacion
                )
                updates_performed["kardex_updates"] += kardex_updated

            return Response(
                {
                    "error": 0,
                    "message": "Cálculo completado y base de datos actualizada exitosamente",
                    "data": {
                        "kardex": kardex,
                        "item": item,
                        "fecha_modificacion": fecha_modificacion,
                        "calculation_results": results,
                        "updates_performed": updates_performed,
                        "summary": {
                            "total_items": len(results),
                            "total_participants": sum(
                                len(item["participants"]) for item in results
                            ),
                            "participants_with_percentage": sum(
                                len([p for p in item["participants"] if p["gets_percentage"]])
                                for item in results
                            ),
                            "participants_without_percentage": sum(
                                len([p for p in item["participants"] if not p["gets_percentage"]])
                                for item in results
                            ),
                            "total_database_updates": sum(updates_performed.values()),
                        },
                    },
                }
            )

        except Exception as e:
            return Response(
                {"error": 1, "errorDescription": f"Error en cálculo: {str(e)}"}, status=500
            )

    def _divide_evenly(self, count: int, total_amount: float) -> List[float]:
        """
        Divide amount evenly among participants, handling rounding issues.
        Based on the PHP divide() function.
        """
        if count >= 2:
            # Calculate base division
            base_amount = round(total_amount / count, 2)

            # Check if there's a remainder due to rounding
            total_distributed = base_amount * count
            remainder = round(total_amount - total_distributed, 2)

            # Create array with base amounts
            amounts = [base_amount] * count

            # Add remainder to the last participant if needed
            if remainder != 0:
                amounts[-1] += remainder

            return amounts
        else:
            # If only one participant, give them everything
            return [total_amount] if count == 1 else []

    @action(detail=False, methods=["post"])
    def execute_calculation(self, request):
        """
        Execute the actual database updates for percentage calculation.
        This performs the updates that were previewed in the calculate endpoint.
        """
        try:
            kardex = request.data.get("kardex")
            if not kardex:
                return Response({"error": 1, "errorDescription": "Kardex is required"}, status=400)

            # Get current date for modification
            fecha_modificacion = datetime.now().strftime("%d/%m/%Y")

            # Get detalle_actos_kardex records for this kardex using ORM
            detalle_actos = models.DetalleActosKardex.objects.filter(kardex=kardex)

            if not detalle_actos.exists():
                return Response(
                    {"error": 1, "errorDescription": "No se encontraron actos para este kardex"},
                    status=404,
                )

            updates_performed = {
                "patrimonial_updates": 0,
                "contratantesxacto_condition_updates": 0,
                "contratantesxacto_percentage_updates": 0,
                "kardex_updates": 0,
            }

            with transaction.atomic():  # Ensure all updates succeed or fail together

                for detalle_acto in detalle_actos:
                    item = detalle_acto.item
                    kardex_val = detalle_acto.kardex
                    idtipoacto = detalle_acto.idtipoacto

                    # 1. Update patrimonial table - set item field
                    patrimonial_updated = models.Patrimonial.objects.filter(
                        kardex=kardex_val, idtipoacto=idtipoacto
                    ).update(item=item)
                    updates_performed["patrimonial_updates"] += patrimonial_updated

                    # 2. Update contratantesxacto conditions from actocondicion
                    acto_condiciones = models.Actocondicion.objects.filter(idtipoacto=idtipoacto)

                    for condicion in acto_condiciones:
                        contratantes_updated = models.Contratantesxacto.objects.filter(
                            idcondicion=condicion.idcondicion,
                            kardex=kardex_val,
                            idtipoacto=idtipoacto,
                        ).update(
                            parte=condicion.parte,
                            uif=condicion.uif,
                            formulario=_contratantesxacto_formulario_from_acto(condicion),
                            montop=condicion.montop or "",
                        )
                        updates_performed[
                            "contratantesxacto_condition_updates"
                        ] += contratantes_updated

                    # 3. Calculate and update percentages and amounts
                    # Get participants by parte
                    vendedores = models.Contratantesxacto.objects.filter(
                        kardex=kardex_val, parte="1"
                    )
                    numero_vendedores = vendedores.count()

                    compradores = models.Contratantesxacto.objects.filter(
                        kardex=kardex_val, parte="2"
                    )
                    numero_compradores = compradores.count()

                    # Get transaction amount
                    try:
                        patrimonial = models.Patrimonial.objects.get(
                            idtipoacto=idtipoacto, item=item
                        )
                        importe_trans = (
                            float(patrimonial.importetrans) if patrimonial.importetrans else 0
                        )
                    except models.Patrimonial.DoesNotExist:
                        importe_trans = 0

                    # Calculate distributions
                    vendedor_percentages = self._divide_evenly(numero_vendedores, 100)
                    comprador_percentages = self._divide_evenly(numero_compradores, 100)
                    vendedor_amounts = self._divide_evenly(numero_vendedores, importe_trans)
                    comprador_amounts = self._divide_evenly(numero_compradores, importe_trans)

                    # Update vendedores percentages and amounts
                    for i, vendedor in enumerate(vendedores):
                        percentage = vendedor_percentages[i] if i < len(vendedor_percentages) else 0
                        amount = vendedor_amounts[i] if i < len(vendedor_amounts) else 0

                        models.Contratantesxacto.objects.filter(
                            item=item,
                            parte="1",
                            idcontratante=vendedor.idcontratante,
                            idtipoacto=idtipoacto,
                        ).update(porcentaje=str(percentage), monto=str(amount))
                        updates_performed["contratantesxacto_percentage_updates"] += 1

                    # Update compradores percentages and amounts
                    for i, comprador in enumerate(compradores):
                        percentage = (
                            comprador_percentages[i] if i < len(comprador_percentages) else 0
                        )
                        amount = comprador_amounts[i] if i < len(comprador_amounts) else 0

                        models.Contratantesxacto.objects.filter(
                            item=item,
                            parte="2",
                            idcontratante=comprador.idcontratante,
                            idtipoacto=idtipoacto,
                        ).update(porcentaje=str(percentage), monto=str(amount))
                        updates_performed["contratantesxacto_percentage_updates"] += 1

                # 4. Update kardex modification date
                kardex_updated = models.Kardex.objects.filter(kardex=kardex).update(
                    fecha_modificacion=fecha_modificacion
                )
                updates_performed["kardex_updates"] += kardex_updated

            return Response(
                {
                    "error": 0,
                    "message": "Cálculo ejecutado exitosamente",
                    "data": {
                        "kardex": kardex,
                        "fecha_modificacion": fecha_modificacion,
                        "updates_performed": updates_performed,
                        "total_updates": sum(updates_performed.values()),
                    },
                }
            )

        except Exception as e:
            return Response(
                {"error": 1, "errorDescription": f"Error ejecutando cálculo: {str(e)}"}, status=500
            )

    @action(detail=False, methods=["get"], url_path="pdt-file")
    def generate_pdt_file(self, request):
        """
        Generate PDT files (.lib, .act, .bie, etc.)

        Query Parameters:
        - initialDate: Start date (DD/MM/YYYY)
        - finalDate: End date (DD/MM/YYYY)
        - fileType: Type of file to generate:
            1 = Actos (.act)
            2 = Bienes (.bie)
            3 = Otorgantes (.otg)
            4 = Medio de Pago (.mpa)
            5 = Formulario (.for)
            6 = Libros (.lib)
        - typeKardex: (Optional) Type of kardex to filter by:
            1 = Escritura
            3 = Transferencia
            4 = Garantía
            logger
        """
        try:
            # Get and validate parameters
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")
            file_type = request.query_params.get("fileType")
            type_kardex = request.query_params.get("typeKardex")

            print("initial_date", initial_date)
            print("final_date", final_date)

            # Validate required parameters
            if not all([initial_date, final_date, file_type]):
                return Response(
                    {"error": "initialDate, finalDate, and fileType are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate file type
            try:
                file_type = int(file_type)
                if file_type not in [
                    PdtFileService.FILE_TYPE_ACT,
                    PdtFileService.FILE_TYPE_BIE,
                    PdtFileService.FILE_TYPE_OTG,
                    PdtFileService.FILE_TYPE_MPA,
                    PdtFileService.FILE_TYPE_FORM,
                    PdtFileService.FILE_TYPE_LIB,
                ]:
                    return Response(
                        {"error": "Invalid fileType. Must be between 1 and 6"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except ValueError:
                return Response(
                    {"error": "fileType must be a number"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Validate type_kardex if provided
            if type_kardex:
                try:
                    type_kardex = int(type_kardex)
                    if type_kardex not in [1, 3, 4]:  # Valid kardex types
                        return Response(
                            {
                                "error": "Invalid typeKardex. Must be 1 (Escritura), 3 (Transferencia), or 4 (Garantía)"
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                except ValueError:
                    return Response(
                        {"error": "typeKardex must be a number"}, status=status.HTTP_400_BAD_REQUEST
                    )

            # Validate dates
            try:
                # Try DD/MM/YYYY format first
                datetime.strptime(initial_date, "%d/%m/%Y")
                datetime.strptime(final_date, "%d/%m/%Y")
            except ValueError:
                try:
                    # Try YYYY-MM-DD format as fallback
                    initial_date = datetime.strptime(initial_date, "%Y-%m-%d").strftime("%d/%m/%Y")
                    final_date = datetime.strptime(final_date, "%Y-%m-%d").strftime("%d/%m/%Y")
                except ValueError:
                    return Response(
                        {"error": "Invalid date format. Use DD/MM/YYYY or YYYY-MM-DD"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Validate date range
            start_date = datetime.strptime(initial_date, "%d/%m/%Y")
            end_date = datetime.strptime(final_date, "%d/%m/%Y")
            if start_date > end_date:
                return Response(
                    {"error": "initialDate cannot be later than finalDate"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Generate PDT file
            try:
                pdt_service = PdtFileService(
                    initial_date=initial_date,
                    final_date=final_date,
                    file_type=file_type,
                    type_kardex=type_kardex,
                )

                response = pdt_service.generate_file()

                # Add CORS headers if needed
                response["Access-Control-Expose-Headers"] = "Content-Disposition"

                return response

            except ValueError as e:
                # Handle known validation errors
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                # Log unexpected errors
                print(f"Error generating PDT file: {str(e)}")
                return Response(
                    {"error": "Error generating PDT file", "detail": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as e:
            print(f"Error in generate_pdt_file: {str(e)}")
            return Response(
                {"error": "Internal server error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TipoKarViewSet(ModelViewSet):
    """
    ViewSet for the TipoKar model.
    """

    queryset = models.Tipokar.objects.all()
    serializer_class = serializers.TipoKarSerializer


class ContratantesViewSet(ModelViewSet):
    """
    ViewSet for the Contratante model.
    """

    queryset = models.Contratantes.objects.all()
    serializer_class = serializers.ContratantesSerializer
    pagination_class = pagination.KardexPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.CreateContratantesSerializer
        return serializers.ContratantesSerializer

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        Update a Contratante and its related Contratantesxacto records.
        This method will update the Contratante and ensure that the related
        Contratantesxacto records are also updated based on the provided conditions.
        """

        instance = self.get_object()
        data = request.data

        data_condition_pairs = _normalize_condicion_entries(data.get("condicion"))
        instance_condition_pairs = _normalize_condicion_entries(instance.condicion)

        set_data = set(data_condition_pairs)
        set_conditions = set(instance_condition_pairs)

        # Check if the conditions in the data are already in the instance
        only_in_set_data = set_data - set_conditions

        for idcondicion, item in only_in_set_data:
            acto_condicion = models.Actocondicion.objects.get(idcondicion=idcondicion)
            models.Contratantesxacto.objects.get_or_create(
                kardex=data.get("kardex"),
                idtipoacto=acto_condicion.idtipoacto,
                idcontratante=instance.idcontratante,
                item=item,
                idcondicion=idcondicion,
                defaults={
                    "idtipkar": acto_condicion.idtipoacto,
                    "parte": acto_condicion.parte,
                    "porcentaje": "",
                    "uif": acto_condicion.uif,
                    "formulario": acto_condicion.formulario,
                    "monto": "",
                    "opago": "",
                    "ofondo": "",
                    "montop": acto_condicion.montop or "",
                },
            )

        only_in_set_conditions = set_conditions - set_data
        for idcondicion, item in only_in_set_conditions:
            print("removing contratantexacto for condition:", f"{idcondicion}.{item}")
            # If the condition is in the instance but not in the data, delete only that exact row
            models.Contratantesxacto.objects.filter(
                idcontratante=instance.idcontratante,
                idcondicion=idcondicion,
                kardex=instance.kardex,
                item=item,
            ).delete()

        # conditions_formatted_array = []
        # for single_condition in  data.get('condicion').split('/'):
        #     if single_condition:
        #         conditions_formatted_array.append(f"{single_condition}.{item}/")

        # data['condicion'] = ''.join(conditions_formatted_array)

        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _reset_sisgen_for_kardex(instance.kardex)
        _refresh_kardex_fechaconclusion_from_contratantes(instance.kardex)
        return Response(serializer.data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """
        Delete a Contratante and all related Cliente2 and Contratantesxacto records.
        """
        instance = self.get_object()

        # BEFORE REMOVE THE CONTRATANTE CHECK IF
        # - idcontratanterp filled
        #   - if so remove representante with the current contratante id
        # - check for all contratantes with the same kardex of the current one and if they have idcontratanterp field with the id of the current contratante
        #   - if so remove the idcontratanterp field from those contratantes as well as the representantes
        # Optional: delete related data
        models.Cliente2.objects.filter(idcontratante=instance.idcontratante).delete()
        models.Contratantesxacto.objects.filter(idcontratante=instance.idcontratante).delete()

        instance.delete()
        _reset_sisgen_for_kardex(instance.kardex)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a Contratante and a Cliente2 based on the provided idcliente.
        This method will generate new IDs for Contratante and Cliente2,
        and ensure that Cliente2 is not orphaned.
        """
        idcliente = request.query_params.get("idcliente")
        data = request.data

        if not idcliente:
            return Response({"error": "Debe proporcionar el idcliente"}, status=400)

        # Step 1: Get Cliente1 info from numdoc

        cliente1 = models.Cliente.objects.filter(idcliente=idcliente).first()
        if not cliente1:
            return Response(
                {"error": "No se encontró Cliente1 con ese número de documento"}, status=404
            )

        # Step 2: Try up to 5 times to generate valid IDs
        for attempt in range(5):
            try:
                sid = transaction.savepoint()
                # Generate IDs
                idcontratante = utils.generate_new_id(models.Contratantes, "idcontratante")
                idcliente2 = utils.generate_new_id(models.Cliente2, "idcliente")

                condition_pairs = _normalize_condicion_entries(data.get("condicion"))
                for idcondicion, item in condition_pairs:
                    acto_condicion = models.Actocondicion.objects.get(idcondicion=idcondicion)
                    models.Contratantesxacto.objects.get_or_create(
                        kardex=data.get("kardex"),
                        idtipoacto=acto_condicion.idtipoacto,
                        idcontratante=idcontratante,
                        item=item,
                        idcondicion=idcondicion,
                        defaults={
                            "idtipkar": acto_condicion.idtipoacto,
                            "parte": acto_condicion.parte,
                            "porcentaje": "",
                            "uif": acto_condicion.uif,
                            "formulario": _contratantesxacto_formulario_from_acto(acto_condicion),
                            "monto": "",
                            "opago": "",
                            "ofondo": "",
                            "montop": acto_condicion.montop or "",
                        },
                    )

                # Check orphan
                if models.Cliente2.objects.filter(idcontratante=idcontratante).exists():
                    models.Cliente2.objects.filter(idcontratante=idcontratante).delete()
                    continue  # Try again with a new idcontratante

                # Create Contratante
                contratante_serializer = self.get_serializer(data=request.data)
                contratante_serializer.is_valid(raise_exception=True)
                contratante_serializer.save(idcontratante=idcontratante)

                cliente2_data = {
                    "idcliente": idcliente2,
                    "idcontratante": idcontratante,
                    "tipper": cliente1.tipper,
                    "apepat": cliente1.apepat,
                    "apemat": cliente1.apemat,
                    "prinom": cliente1.prinom,
                    "segnom": cliente1.segnom,
                    "nombre": f"{cliente1.prinom} {cliente1.segnom} {cliente1.apepat} {cliente1.apemat}",
                    "direccion": cliente1.direccion,
                    "idtipdoc": cliente1.idtipdoc,
                    "numdoc": cliente1.numdoc,
                    "email": cliente1.email,
                    "telfijo": cliente1.telfijo,
                    "telcel": cliente1.telcel,
                    "telofi": cliente1.telofi or "",
                    "sexo": cliente1.sexo or "",
                    "idestcivil": cliente1.idestcivil or 0,
                    "natper": cliente1.nacionalidad or "",
                    "conyuge": "",
                    "nacionalidad": cliente1.nacionalidad or "",
                    "idprofesion": cliente1.idprofesion or 0,
                    "detaprofesion": cliente1.detaprofesion or "",
                    "idcargoprofe": cliente1.idcargoprofe or 0,
                    "profocupa": cliente1.detaprofesion or "",
                    "dirfer": cliente1.direccion,
                    "idubigeo": cliente1.idubigeo or ".",
                    "cumpclie": cliente1.cumpclie or ".",
                    "razonsocial": cliente1.razonsocial or "",
                    "fechaing": "",  # This will be set later
                    "residente": cliente1.residente or "0",
                    "tipocli": "0",
                    "profesion_plantilla": cliente1.detaprofesion or "",
                    "ubigeo_plantilla": cliente1.idubigeo or "",
                    "fechaconstitu": "",  # This will be set later
                    "idsedereg": 1,  # Assuming this is a constant value
                    "domfiscal": cliente1.domfiscal or "",
                    "telempresa": cliente1.telofi or "",
                    "mailempresa": cliente1.email or "",
                    "contacempresa": cliente1.contacempresa or "",
                    "numregistro": cliente1.numregistro or "",
                    "numpartida": cliente1.numpartida or "",
                    "actmunicipal": cliente1.actmunicipal or "",
                    "impeingre": "",
                    "impnumof": "",
                    "impeorigen": "",
                    "impentidad": "",
                    "impremite": "",
                    "impmotivo": "",
                    "docpaisemi": "",
                }

                cliente2_serializer = serializers.Cliente2Serializer(data=cliente2_data)
                cliente2_serializer.is_valid(raise_exception=True)
                cliente2_serializer.save()
                _reset_sisgen_for_kardex(data.get("kardex"))

                # Return created contratante
                transaction.savepoint_commit(sid)
                return Response(contratante_serializer.data, status=status.HTTP_201_CREATED)

            except Exception as e:
                transaction.savepoint_rollback(sid)
                if attempt == 4:
                    return Response(
                        {"error": f"Error al crear contratante/cliente2: {str(e)}"}, status=400
                    )
                continue

        return Response(
            {"error": "No se pudo generar un ID válido tras varios intentos"}, status=400
        )

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get Contratantes by Kardex.
        """
        kardex = request.query_params.get("kardex")
        if not kardex:
            return Response({"error": "kardex parameter is required."}, status=400)
        contratantes = models.Contratantes.objects.filter(kardex=kardex)
        contratante_ids = set(c.idcontratante for c in contratantes)

        contratantes_tipoactos = set(c.condicion.split(".")[0] for c in contratantes)

        print("contratantes_tipoactos", contratantes_tipoactos)

        condicion_map = {
            c["idcondicion"]: c
            for c in models.Actocondicion.objects.filter(
                idcondicion__in=contratantes_tipoactos
            ).values("idcondicion", "condicion")
        }

        clientes_map = {
            c["idcontratante"]: c
            for c in models.Cliente2.objects.filter(idcontratante__in=contratante_ids).values(
                "idcontratante", "nombre", "numdoc", "idcliente", "razonsocial"
            )
        }

        if not contratantes.exists():
            return Response({}, status=200)

        serializer = serializers.ContratantesKardexSerializer(
            contratantes,
            many=True,
            context={"clientes_map": clientes_map, "condicion_map": condicion_map},
        )
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def calulcate(self, request):
        pass


class ContratantesxactoViewSet(ModelViewSet):
    """
    ViewSet for the Contratantesxacto model.
    """

    queryset = models.Contratantesxacto.objects.all()
    serializer_class = serializers.ContratantesxactoSerializer
    pagination_class = pagination.KardexPagination

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        instance = self.get_object()
        _reset_sisgen_for_kardex(instance.kardex)
        return response

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        kardex_code = ""
        if isinstance(getattr(response, "data", None), dict):
            kardex_code = response.data.get("kardex")
        _reset_sisgen_for_kardex(kardex_code)
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        kardex_code = instance.kardex
        response = super().destroy(request, *args, **kwargs)
        _reset_sisgen_for_kardex(kardex_code)
        return response

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get Contratantesxacto records by kardex.
        """
        kardex = request.query_params.get("kardex")
        if not kardex:
            return Response({"error": "kardex parameter is required."}, status=400)

        contratantesxacto = models.Contratantesxacto.objects.filter(kardex=kardex)

        if not contratantesxacto.exists():
            return Response({}, status=200)

        contratantes_ids = set(c.idcontratante for c in contratantesxacto)

        contratantes_tipoactos = set(c.idcondicion for c in contratantesxacto)

        renta = models.Renta.objects.filter(idcontratante__in=contratantes_ids)
        renta_by_kardex = models.Renta.objects.filter(kardex=kardex)

        print(
            "renta_by_kardex",
            renta_by_kardex.values(
                "idrenta", "kardex", "idcontratante", "pregu1", "pregu2", "pregu3"
            ),
        )

        condicion_map = {
            c["idcondicion"]: c
            for c in models.Actocondicion.objects.filter(
                idcondicion__in=contratantes_tipoactos
            ).values("idcondicion", "condicion")
        }

        clientes_map = {
            c["idcontratante"]: c
            for c in models.Cliente2.objects.filter(idcontratante__in=contratantes_ids).values(
                "idcontratante", "nombre", "numdoc", "idcliente", "razonsocial"
            )
        }

        renta_map = {
            c["idcontratante"]: c
            for c in renta.values(
                "idrenta", "kardex", "idcontratante", "pregu1", "pregu2", "pregu3"
            )
        }

        serializer = serializers.GetContratantesxactoSerializerByKardex(
            contratantesxacto,
            many=True,
            context={
                "clientes_map": clientes_map,
                "condicion_map": condicion_map,
                "renta_map": renta_map,
            },
        )
        return Response(serializer.data)


class ClienteViewSet(ModelViewSet):
    """
    ViewSet for the Cliente model.
    """

    queryset = models.Cliente.objects.all()
    serializer_class = serializers.ClienteSerializer
    pagination_class = pagination.KardexPagination
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.CreateClienteSerializer
        return serializers.ClienteSerializer

    def _log_cliente_post_payload(self, request):
        """
        Log incoming payload for Cliente POST requests.
        """
        print("DEBUG _log_cliente_post_payload method called")
        try:
            payload = request.data.copy()
            if hasattr(payload, "dict"):
                payload = payload.dict()
            elif not isinstance(payload, dict):
                payload = dict(payload)
            # Keep both logger + stdout print so it is visible in all environments.
            logger.warning("Cliente POST payload received: %s", payload)
            print("DEBUG Cliente POST payload received:", payload)
            return payload
        except Exception as exc:
            logger.warning("Could not log Cliente POST payload: %s", exc)
            print("DEBUG Could not log Cliente POST payload:", exc)
            return {}

    @action(detail=False, methods=["get"])
    def by_name(self, request):
        """
        Get Cliente records by name or razonsocial.
        """
        name = request.query_params.get("name")
        if not name:
            return Response({"error": "name parameter is required."}, status=400)
        # filter by nombre and razonsocial
        clientes = models.Cliente.objects.filter(
            Q(nombre__icontains=name) | Q(razonsocial__icontains=name)
        )
        if not clientes.exists():
            return Response({}, status=200)

        paginator = pagination.KardexPagination()
        result = paginator.paginate_queryset(clientes, request)
        serializer = serializers.ClienteSerializer(result, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=["get"])
    def by_dni(self, request):
        """
        Get Cliente records by DNI.
        """
        dni = request.query_params.get("dni")
        if not dni:
            return Response({"error": "dni parameter is required."}, status=400)

        clientes = models.Cliente.objects.filter(numdoc=dni)
        if not clientes.exists():
            return Response({}, status=200)

        serializer = serializers.ClienteSerializer(clientes[len(clientes) - 1])
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def by_ruc(self, request):
        """
        Get Cliente records by RUC.
        """
        ruc = request.query_params.get("ruc")
        if not ruc:
            return Response({"error": "ruc parameter is required."}, status=400)

        clientes = models.Cliente.objects.filter(numdoc=ruc)
        if not clientes.exists():
            return Response({}, status=200)

        serializer = serializers.ClienteSerializer(clientes[len(clientes) - 1])
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Create a Cliente record.
        """
        idtipdoc = request.data.get("idtipdoc")
        if idtipdoc == 10:
            # Generate CODJU for juridical persons (like PHP script)
            codju_count = models.Cliente.objects.filter(numdoc_plantilla__contains="CODJU").count()
            next_number = codju_count + 1

            # Format as CODJU000001, CODJU000002, etc.
            new_codju = f"CODJU{str(next_number).zfill(6)}"

            # Create a mutable copy of the request data
            data = request.data.copy()
            data["numdoc_plantilla"] = new_codju

            # Also ensure numdoc is empty for CODJU records (like PHP)
            if "numdoc" not in data:
                data["numdoc"] = ""

            # Create serializer with modified data
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        # working on this
        """
        Update a Cliente record.
        """
        idestcivil = request.data.get("idestcivil")
        conyuge_data = request.data.get("conyuge")
        instance = self.get_object()
        conyuge_instance = instance.conyuge

        update_civil = idestcivil != instance.idestcivil or idestcivil == 2 or idestcivil == 4
        from_any_to_married = idestcivil == 2 or idestcivil == 4

        change_conyuge = conyuge_data != conyuge_instance
        if update_civil and change_conyuge:
            # update conyugue
            if from_any_to_married:
                if conyuge_data:
                    print("conyuge_data", conyuge_data)
                    conyuge_client = models.Cliente.objects.get(idcliente=conyuge_data)
                    conyuge_client.conyuge = instance.idcliente
                    conyuge_client.idestcivil = idestcivil
                    conyuge_client.save()

        response = super().update(request, *args, **kwargs)
        _reset_sisgen_for_kardex(instance.kardex)
        return response


class Cliente2ViewSet(ModelViewSet):
    """
    ViewSet for the Cliente2 model.
    """

    queryset = models.Cliente2.objects.all()
    serializer_class = serializers.Cliente2Serializer
    pagination_class = pagination.KardexPagination
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.CreateCliente2Serializer
        return serializers.Cliente2Serializer

    @staticmethod
    def _debug_cliente2_payload(request, action_name: str) -> None:
        """Temporary debug trace to inspect incoming cliente2 update payloads."""
        payload = request.data if hasattr(request, "data") else {}
        if hasattr(payload, "dict"):
            try:
                payload = payload.dict()
            except Exception:
                payload = dict(payload)
        if not isinstance(payload, dict):
            print(f"DEBUG cliente2 {action_name}: payload type={type(payload).__name__}")
            return

        keys = sorted(payload.keys())
        print(f"DEBUG cliente2 {action_name}: fields={keys}")
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str):
                print(
                    f"DEBUG cliente2 {action_name}: {key}={value!r} len={len(value)}"
                )
            else:
                print(
                    f"DEBUG cliente2 {action_name}: {key}={value!r} type={type(value).__name__}"
                )

    def update(self, request, *args, **kwargs):
        self._debug_cliente2_payload(request, "PUT")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._debug_cliente2_payload(request, "PATCH")
        return super().partial_update(request, *args, **kwargs)

    @transaction.atomic
    def perform_update(self, serializer):
        updated_cliente2 = serializer.save()
        detaprofesion_in = serializer.validated_data.get("detaprofesion", None)
        if detaprofesion_in is not None:
            # Force requested detail in cliente2 as well.
            models.Cliente2.objects.filter(pk=updated_cliente2.pk).update(
                detaprofesion=detaprofesion_in
            )
        # DB triggers/procedures can mutate cliente2 fields after UPDATE.
        # Reload to sync cliente with the true persisted state.
        updated_cliente2.refresh_from_db()
        overrides = {}
        if detaprofesion_in is not None:
            overrides["detaprofesion"] = detaprofesion_in
        _sync_cliente_from_cliente2(updated_cliente2, force_overrides=overrides)

    @action(detail=False, methods=["get"])
    def by_dni(self, request):
        """
        Get Cliente2 records by DNI.
        """
        dni = request.query_params.get("dni")
        if not dni:
            return Response({"error": "dni parameter is required."}, status=400)

        clientes = models.Cliente2.objects.filter(numdoc=dni)
        if not clientes.exists():
            return Response({}, status=200)

        serializer = serializers.Cliente2Serializer(clientes[len(clientes) - 1])
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def by_contratante(self, request):
        """
        Get Cliente2 records by Contratante ID.
        """
        idcontratante = request.query_params.get("idcontratante")
        if not idcontratante:
            return Response({"error": "idcontratante parameter is required."}, status=400)
        cliente = models.Cliente2.objects.get(idcontratante=idcontratante)
        if not cliente:
            return Response({}, status=200)
        serializer = serializers.Cliente2Serializer(cliente)
        return Response(serializer.data)


class TiposDeActosViewSet(ModelViewSet):
    """
    ViewSet for the TiposDeActos model.
    """

    queryset = models.Tiposdeacto.objects.all()
    serializer_class = serializers.TiposDeActosSerializer
    permission_classes = [IsAuthenticated]


class ActoCondicionViewSet(ModelViewSet):
    """
    ViewSet for the ActoCondicion model.

    ``POST`` (create): ``idcondicion`` is auto-generated (max numeric id + 1, as legacy PHP).
    ``parte`` is mirrored into ``parte_generacion`` on create and update when ``parte`` is sent.
    ``condicion``, ``condicionsisgen``, and ``codconsisgen`` are normalized to uppercase on save.
    ``parte``, ``formulario``, ``montop``, SISGEN fields (``condicionsisgen``, ``codconsisgen``)
    use ``""`` when missing or null (no NULL inserts).
    ``descripcion`` is always set equal to ``condicion`` on save.
    """

    queryset = models.Actocondicion.objects.all().order_by("idcondicion")
    serializer_class = serializers.ActoCondicionSerializer

    @action(detail=False, methods=["get"])
    def by_tipoacto(self, request):
        """
        Get ActoCondicion records by tipoacto.
        """
        tipoacto = request.query_params.get("tipoacto")
        print()
        if not tipoacto:
            return Response({"error": "tipoacto parameter is required."}, status=400)

        acto_condiciones = models.Actocondicion.objects.filter(idtipoacto=tipoacto)

        if not acto_condiciones.exists():
            return Response({}, status=200)

        serializer = serializers.ActoCondicionSerializer(acto_condiciones, many=True)
        return Response(serializer.data)


class DetalleActosKardexViewSet(ModelViewSet):
    """
    ViewSet for the DetalleActosKardex model.
    """

    queryset = models.DetalleActosKardex.objects.all()
    serializer_class = serializers.DetalleActosKardexSerializer
    pagination_class = pagination.KardexPagination
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def by_kardex_tipoacto(self, request):
        """
        Get DetalleActosKardex records by kardex and tipoacto.
        """
        kardex = request.query_params.get("kardex")
        tipoacto = request.query_params.get("tipoacto")

        if not kardex or not tipoacto:
            return Response({"error": "kardex and tipoacto parameters are required."}, status=400)

        try:
            detalle_actos = models.DetalleActosKardex.objects.get(
                kardex=kardex, idtipoacto=tipoacto
            )

        except models.DetalleActosKardex.DoesNotExist:
            return Response(
                {"error": "No DetalleActosKardex found for the given kardex and tipoacto."},
                status=404,
            )

        serializer = serializers.DetalleActosKardexSerializer(detalle_actos)
        return Response(serializer.data)


class TbAbogadoViewSet(ModelViewSet):
    """
    ViewSet for the TbAbogado model.
    """

    queryset = models.TbAbogado.objects.all()
    serializer_class = serializers.TbAbogadoSerializer
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a TbAbogado instance with auto-generated idabogado.
        idabogado format: 10-digit zero-padded incremental value.
        """
        for attempt in range(5):
            try:
                sid = transaction.savepoint()
                last_record = models.TbAbogado.objects.order_by("-idabogado").first()
                if last_record and str(last_record.idabogado).strip():
                    try:
                        next_id = int(str(last_record.idabogado).strip()) + 1
                    except ValueError:
                        next_id = 1
                else:
                    next_id = 1

                data = request.data.copy()
                data["idabogado"] = f"{next_id:010d}"
                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                headers = self.get_success_headers(serializer.data)
                return Response(
                    serializer.data, status=status.HTTP_201_CREATED, headers=headers
                )
            except Exception as e:
                transaction.savepoint_rollback(sid)
                if attempt == 4:
                    raise
                continue


class NacionalidadesViewSet(ModelViewSet):
    """
    ViewSet for the Nacionalidades model.
    """

    queryset = models.Nacionalidades.objects.all()
    serializer_class = serializers.NacionalidadesSerializer
    permission_classes = [IsAuthenticated]


class ProfesionesViewSet(ModelViewSet):
    """
    ViewSet for the Profesiones model.
    """

    queryset = models.Profesiones.objects.all()
    serializer_class = serializers.ProfesionesSerializer
    permission_classes = [IsAuthenticated]


class CargoprofeViewSet(ModelViewSet):
    """
    ViewSet for the Cargoprofe model.
    """

    queryset = models.Cargoprofe.objects.all()
    serializer_class = serializers.CargoprofeSerializer
    permission_classes = [IsAuthenticated]


class UbigeoViewSet(ModelViewSet):
    """
    ViewSet for the Ubigeo model.
    """

    queryset = models.Ubigeo.objects.all()
    serializer_class = serializers.UbigeoSerializer
    permission_classes = [IsAuthenticated]
    # pagination_class = pagination.KardexPagination


class SedesRegistralesViewSet(ModelViewSet):
    """
    ViewSet for the SedesRegistrales model.
    """

    queryset = models.Sedesregistrales.objects.all()
    serializer_class = serializers.SedesregistralesSerializer
    permission_classes = [IsAuthenticated]


class RepresentantesViewSet(ModelViewSet):
    """
    ViewSet for the Representantes model.
    """

    queryset = models.Representantes.objects.all()
    serializer_class = serializers.RepresentantesSerializer
    pagination_class = pagination.KardexPagination
    permission_classes = [IsAuthenticated]


class PatrimonialViewSet(ModelViewSet):
    """
    ViewSet for the Patrimonial model.
    """

    queryset = models.Patrimonial.objects.all()
    serializer_class = serializers.PatrimonialSerializer
    pagination_class = pagination.KardexPagination

    def update(self, request, *args, **kwargs):
        """Update a Patrimonial record.
        This method will ensure that the itemmp field is not modified.
        """
        data = request.data
        instance = self.get_object()

        if data.get("idtipoacto") != instance.idtipoacto:
            vehicular = models.Detallevehicular.objects.filter(
                kardex=instance.kardex, idtipacto=instance.idtipoacto
            ).first()
            if vehicular:
                return Response(
                    {
                        "error": "No se puede cambiar el idtipoacto de un Patrimonial que tiene un DetalleVehicular asociado."
                    },
                    status=400,
                )

        return super().update(request, *args, **kwargs)

    # remove patrimonial and also remove medio de pago
    def destroy(self, request, *args, **kwargs):
        """
        Delete a Patrimonial record and its related Detallemediopago and DetalleVehicular records.
        """
        instance = self.get_object()
        kardex = instance.kardex
        idtipoacto = instance.idtipoacto

        # Remove related Detallemediopago records
        models.Detallemediopago.objects.filter(itemmp=instance.itemmp).delete()

        # Remove related DetalleVehicular records
        models.Detallevehicular.objects.filter(kardex=kardex, idtipacto=idtipoacto).delete()

        # Remove the Patrimonial record
        instance.delete()
        _reset_sisgen_for_kardex(kardex)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @transaction.atomic
    def create(self, request, *args, **kwargs):

        for attempt in range(5):
            try:
                sid = transaction.savepoint()
                # Generate ID
                itemmp = utils.generate_new_id(models.Patrimonial, "itemmp", 6)

            except Exception as e:
                transaction.savepoint_rollback(sid)
                if attempt == 4:
                    return Response({"error": f"Error al crear Patrimonial: {str(e)}"}, status=400)
                continue

            data = request.data
            data["itemmp"] = itemmp
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            _reset_sisgen_for_kardex(serializer.instance.kardex)

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(
            {"error": "No se pudo generar un ID válido tras varios intentos"}, status=400
        )

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get Patrimonial records by Kardex.
        """
        kardex = request.query_params.get("kardex")
        if not kardex:
            return Response({"error": "kardex parameter is required."}, status=400)

        patrimonial = models.Patrimonial.objects.filter(kardex=kardex)
        if not patrimonial.exists():
            return Response([], status=200)

        serializer = serializers.PatrimonialSerializer(patrimonial, many=True)
        return Response(serializer.data)


class DetalleVehicularViewSet(ModelViewSet):
    """
    ViewSet for the DetalleVehicular model.
    """

    queryset = models.Detallevehicular.objects.all()
    serializer_class = serializers.DetallevehicularSerializer
    pagination_class = pagination.KardexPagination

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if isinstance(getattr(response, "data", None), dict):
            _reset_sisgen_for_kardex(response.data.get("kardex"))
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        instance = self.get_object()
        _reset_sisgen_for_kardex(instance.kardex)
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        kardex_code = instance.kardex
        response = super().destroy(request, *args, **kwargs)
        _reset_sisgen_for_kardex(kardex_code)
        return response

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get DetalleVehicular records by Kardex.
        """
        kardex = request.query_params.get("kardex")
        idtipoacto = request.query_params.get("idtipoacto")
        if not kardex:
            return Response({"error": "kardex parameter is required."}, status=400)

        detalle_vehicular = models.Detallevehicular.objects.filter(
            kardex=kardex, idtipacto=idtipoacto
        )
        if not detalle_vehicular.exists():
            return Response([], status=200)

        serializer = serializers.DetallevehicularSerializer(detalle_vehicular, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def by_numplaca(self, request):
        """
        Get DetalleVehicular records by numplaca.
        """
        numplaca = request.query_params.get("numplaca")
        if not numplaca:
            return Response({"error": "numplaca parameter is required."}, status=400)

        detalle_vehicular = models.Detallevehicular.objects.filter(numplaca=numplaca).first()
        if not detalle_vehicular:
            return Response(
                {"error": "No DetalleVehicular found for the given numplaca."}, status=404
            )

        serializer = serializers.DetallevehicularSerializer(detalle_vehicular)
        return Response(serializer.data)


class DetallebienesViewSet(ModelViewSet):
    """
    ViewSet for the Detallebienes model.
    """

    queryset = models.Detallebienes.objects.all()
    serializer_class = serializers.DetallebienesSerializer
    pagination_class = pagination.KardexPagination

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if isinstance(getattr(response, "data", None), dict):
            _reset_sisgen_for_kardex(response.data.get("kardex"))
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        instance = self.get_object()
        _reset_sisgen_for_kardex(instance.kardex)
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        kardex_code = instance.kardex
        response = super().destroy(request, *args, **kwargs)
        _reset_sisgen_for_kardex(kardex_code)
        return response

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get Detallebienes records by Kardex.
        """
        kardex = request.query_params.get("kardex")
        if not kardex:
            return Response({"error": "kardex parameter is required."}, status=400)

        detalle_bienes = models.Detallebienes.objects.filter(kardex=kardex)
        if not detalle_bienes.exists():
            return Response([], status=200)

        serializer = serializers.DetallebienesSerializer(detalle_bienes, many=True)
        return Response(serializer.data)


class PrediosViewSet(ModelViewSet):
    """
    ViewSet for the Predios model.
    """

    queryset = models.Predios.objects.all()
    serializer_class = serializers.PrediosSerializer
    pagination_class = pagination.KardexPagination

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if isinstance(getattr(response, "data", None), dict):
            _reset_sisgen_for_kardex(response.data.get("kardex"))
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        instance = self.get_object()
        _reset_sisgen_for_kardex(instance.kardex)
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        kardex_code = instance.kardex
        response = super().destroy(request, *args, **kwargs)
        _reset_sisgen_for_kardex(kardex_code)
        return response

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get Predios records by Kardex.
        """
        kardex = request.query_params.get("kardex")
        if not kardex:
            return Response({"error": "kardex parameter is required."}, status=400)

        predios = models.Predios.objects.filter(kardex=kardex)
        if not predios.exists():
            return Response([], status=200)

        serializer = serializers.PrediosSerializer(predios, many=True)
        return Response(serializer.data)


class DetallemediopagoViewSet(ModelViewSet):
    """
    ViewSet for the Detallemediopago model.
    """

    queryset = models.Detallemediopago.objects.all()
    serializer_class = serializers.DetallemediopagoSerializer
    pagination_class = pagination.KardexPagination

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if isinstance(getattr(response, "data", None), dict):
            _reset_sisgen_for_kardex(response.data.get("kardex"))
        return response

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        instance = self.get_object()
        _reset_sisgen_for_kardex(instance.kardex)
        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        kardex_code = instance.kardex
        response = super().destroy(request, *args, **kwargs)
        _reset_sisgen_for_kardex(kardex_code)
        return response

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get Detallemediopago records by Kardex.
        """
        kardex = request.query_params.get("kardex")
        if not kardex:
            return Response({"error": "kardex parameter is required."}, status=400)

        detalle_mediopago = models.Detallemediopago.objects.filter(kardex=kardex)
        if not detalle_mediopago.exists():
            return Response([], status=200)

        serializer = serializers.DetallemediopagoSerializer(detalle_mediopago, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def by_patrimonial(self, request):
        """
        Get Detallemediopago records by Patrimonial itemmp.
        """
        itemmp = request.query_params.get("itemmp")
        if not itemmp:
            return Response({"error": "itemmp parameter is required."}, status=400)

        detalle_mediopago = models.Detallemediopago.objects.filter(itemmp=itemmp)
        if not detalle_mediopago.exists():
            return Response([], status=200)

        serializer = serializers.DetallemediopagoSerializer(detalle_mediopago, many=True)
        return Response(serializer.data)


class TemplateViewSet(ModelViewSet):
    """
    ViewSet for the TplTemplate model.

    URL ``{pk}`` is the database **pkTemplate** value (model field ``pktemplate``), not a
    positional index in a list.

    Optional query params on list only:
    - codeActs: substring match on codeActs
    - fkTypeKardex: exact match on fkTypeKardex (integer)
    - nameTemplate: substring match on nameTemplate (case-insensitive)

    R2 file download (no DB): ``GET .../templates/r2-file/?relative_path=plantillas/foo.docx``
    or ``?folder=plantillas&filename=foo.docx``. DB-backed: ``GET .../templates/{pk}/file/``.
    """

    queryset = models.TplTemplate.objects.all()
    serializer_class = serializers.TemplateSerializer
    pagination_class = pagination.KardexPagination
    lookup_field = "pktemplate"
    lookup_url_kwarg = "pk"

    def get_object(self):
        """
        Resolve detail routes by ``pktemplate`` (pkTemplate).

        Uses ``get_queryset()`` only (not ``filter_queryset``) so list filters /
        filter backends never hide a row on retrieve, update, or file download.
        """
        queryset = self.get_queryset()
        pk_raw = self.kwargs.get(self.lookup_url_kwarg)
        try:
            pk_val = int(pk_raw)
        except (TypeError, ValueError):
            raise Http404(f"Invalid pkTemplate in URL: {pk_raw!r}") from None
        try:
            obj = queryset.get(pktemplate=pk_val)
        except models.TplTemplate.DoesNotExist:
            raise Http404(
                f"No TplTemplate with pkTemplate={pk_val}. "
                "Confirm with GET /api/templates/. "
                "R2-only download: GET /api/templates/r2-file/?relative_path=plantillas/…"
            ) from None
        self.check_object_permissions(self.request, obj)
        return obj

    def get_queryset(self):
        qs = models.TplTemplate.objects.all()
        if self.action != "list":
            return qs

        code_acts = self.request.query_params.get("codeActs")
        fk_type = self.request.query_params.get("fkTypeKardex")
        if fk_type is None:
            fk_type = self.request.query_params.get("fktypekardex")
        name_template = self.request.query_params.get("nameTemplate")

        if code_acts and str(code_acts).strip():
            qs = qs.filter(codeacts__icontains=code_acts.strip())
        if fk_type is not None and str(fk_type).strip() != "":
            try:
                qs = qs.filter(fktypekardex=int(fk_type))
            except (TypeError, ValueError):
                raise ValidationError(
                    {"fkTypeKardex": "Must be a valid integer."},
                )
        if name_template and str(name_template).strip():
            qs = qs.filter(nametemplate__icontains=name_template.strip())
        return qs

    def list(self, request, *args, **kwargs):
        """
        List TplTemplate records with optional filters (see class docstring).
        """
        return super().list(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Delete TplTemplate DB row and best-effort delete its related R2 template file.
        """
        tpl = self.get_object()
        object_key = None
        try:
            object_key = object_key_for_tpl_template_row(tpl.urltemplate, tpl.filename)
        except ValueError:
            # Keep DB delete behavior even if legacy row has no usable file mapping.
            object_key = None

        if object_key:
            try:
                s3 = get_s3_client()
                s3.delete_object(Bucket=get_r2_bucket(), Key=object_key)
                logger.info("TEMPLATE_DELETE: deleted R2 object %s", object_key)
            except Exception as exc:
                # Do not block DB deletion if file is already missing or delete fails.
                logger.warning(
                    "TEMPLATE_DELETE: failed to delete R2 object %s | error=%s",
                    object_key,
                    str(exc),
                )

        tpl.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"], url_path="file")
    def template_file(self, request, pk=None):
        """
        GET: download the .docx from R2 using this template row (resolved key; see
        ``object_key_for_tpl_template_row`` in ducumentation.storage).
        Prefer ``GET .../r2-file/`` when you know the exact R2 path and do not need the DB row.
        """
        tpl = self.get_object()
        return self._download_template_file(tpl)

    @action(detail=False, methods=["get"], url_path="r2-file")
    def r2_file(self, request):
        """
        Download a file directly from R2 — no TplTemplate DB row.

        Query (one of):

        - ``relative_path`` — path after MAIN_URL, e.g. ``plantillas/GARANTIA MOBILIARIA.docx``
        - ``folder`` + ``filename`` — built like ``build_object_key(folder, filename)``
        """
        relative_path = request.query_params.get("relative_path") or request.query_params.get(
            "relativePath"
        )
        folder = request.query_params.get("folder")
        filename = request.query_params.get("filename")

        object_key = None
        attachment_name = "template.docx"

        if relative_path and str(relative_path).strip():
            rel = str(relative_path).strip().lstrip("/")
            if ".." in rel:
                return Response({"detail": "relative_path must not contain '..'"}, status=400)
            try:
                object_key = full_object_key_from_stored_relative(rel)
            except ValueError as e:
                return Response({"detail": str(e)}, status=400)
            attachment_name = rel.split("/")[-1] or attachment_name
        elif folder is not None and str(folder).strip() and filename is not None and str(
            filename
        ).strip():
            try:
                object_key = build_object_key(
                    validate_folder_path(folder),
                    str(filename).strip().lstrip("/"),
                )
            except ValueError as e:
                return Response({"detail": str(e)}, status=400)
            attachment_name = str(filename).strip().split("/")[-1] or attachment_name
        else:
            return Response(
                {
                    "detail": (
                        "Provide relative_path= (e.g. plantillas/foo.docx) "
                        "or folder= and filename=."
                    )
                },
                status=400,
            )

        try:
            data = read_bytes_from_r2(object_key)
        except FileNotFoundError:
            return Response(
                {"detail": "File not found in R2.", "object_key": object_key},
                status=404,
            )
        except Exception as e:
            logger.exception("R2_FILE_GET: read failed")
            return Response({"detail": str(e)}, status=500)

        if not attachment_name.lower().endswith(".docx"):
            attachment_name = f"{attachment_name}.docx"

        return FileResponse(
            BytesIO(data),
            as_attachment=True,
            filename=attachment_name,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )

    def _download_template_file(self, tpl):
        try:
            object_key = object_key_for_tpl_template_row(tpl.urltemplate, tpl.filename)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        try:
            data = read_bytes_from_r2(object_key)
        except FileNotFoundError:
            return Response(
                {"detail": "Template file not found in R2.", "object_key": object_key},
                status=404,
            )
        except Exception as e:
            logger.exception("TEMPLATE_FILE_GET: R2 read failed")
            return Response({"detail": str(e)}, status=500)
        name = (tpl.filename or "template.docx").strip() or "template.docx"
        resp = FileResponse(
            BytesIO(data),
            as_attachment=True,
            filename=name,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
        )
        return resp

    def _handle_template_upload(self, request):
        """
        Shared handler for template upload to R2 + DB upsert.
        """
        logger.info("TEMPLATE_UPLOAD: request received")
        logger.info("TEMPLATE_UPLOAD: data keys=%s", list(request.data.keys()))
        logger.info("TEMPLATE_UPLOAD: file keys=%s", list(request.FILES.keys()))

        if "file" not in request.FILES:
            return Response({"error": "file is required (.docx)"}, status=400)

        uploaded_file = request.FILES["file"]
        raw_uploaded_name = str(uploaded_file.name or "").split("/")[-1].split("\\")[-1]
        name_template = request.data.get("nameTemplate") or request.data.get("nametemplate")

        if not raw_uploaded_name.lower().endswith(".docx"):
            return Response({"error": "Only .docx files are allowed"}, status=400)

        # Normalize duplicate suffixes from either provided nameTemplate or filename.
        # Examples: "compra venta(2).docx", "compra venta-2.docx" -> "compra venta.docx".
        template_source = str(name_template).strip() if name_template else raw_uploaded_name
        if template_source.lower().endswith(".docx"):
            template_source = template_source[:-5]
        name_template = sanitize_copy_suffix_base(template_source)

        if not name_template:
            return Response(
                {"error": "nameTemplate is required (or upload a file with a valid name)"},
                status=400,
            )

        folder = default_folder_plantillas()
        sanitized_filename = docx_filename_from_name_template(name_template)
        object_key = build_object_key(folder, sanitized_filename)
        logger.info(
            "TEMPLATE_UPLOAD: original_file=%s sanitized_filename=%s object_key=%s",
            uploaded_file.name,
            sanitized_filename,
            object_key,
        )

        try:
            upload_fileobj_to_r2(uploaded_file, object_key)
            logger.info("TEMPLATE_UPLOAD: upload to R2 successful")
        except Exception as e:
            logger.exception("TEMPLATE_UPLOAD: upload to R2 failed: %s", str(e))
            return Response({"status": "error", "message": f"R2 upload failed: {str(e)}"}, status=500)

        # Keep nametemplate aligned with the requested template name; filename stores .docx
        codeacts = request.data.get("codeActs") or request.data.get("codeacts")
        fktypekardex = request.data.get("fkTypeKardex") or request.data.get("fktypekardex")
        contract = request.data.get("contract")
        urltemplate = f"{folder}/{sanitized_filename}"

        # Upsert by nametemplate to avoid duplicates for same logical template name
        tpl, created = models.TplTemplate.objects.get_or_create(
            nametemplate=name_template.strip(),
            defaults={
                "filename": sanitized_filename,
                "urltemplate": urltemplate,
                "fktypekardex": int(fktypekardex) if fktypekardex else None,
                "codeacts": codeacts if codeacts else None,
                "contract": contract if contract else None,
            },
        )

        tpl.filename = sanitized_filename
        tpl.urltemplate = urltemplate
        if fktypekardex is not None and fktypekardex != "":
            try:
                tpl.fktypekardex = int(fktypekardex)
            except Exception:
                logger.warning("TEMPLATE_UPLOAD: invalid fkTypeKardex=%s", fktypekardex)
        if codeacts is not None and codeacts != "":
            tpl.codeacts = codeacts
        if contract is not None and contract != "":
            tpl.contract = contract
        tpl.save()

        logger.info(
            "TEMPLATE_UPLOAD: DB upsert successful pk=%s created=%s nametemplate=%s filename=%s",
            tpl.pktemplate,
            created,
            tpl.nametemplate,
            tpl.filename,
        )

        return Response(
            {
                "status": "success",
                "message": "Template uploaded",
                "nameTemplate": tpl.nametemplate,
                "filename": tpl.filename,
                "r2_path": object_key,
                "template_id": tpl.pktemplate,
            },
            status=201,
        )

    def create(self, request, *args, **kwargs):
        """
        Support file uploads through the standard POST /templates/ endpoint too.
        If multipart contains a file, route through R2 upload flow.
        """
        if "file" in request.FILES:
            return self._handle_template_upload(request)
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def by_actos(self, request):
        """
        Get TplTemplate records by acto.
        """
        codactos = request.query_params.get("codactos")
        if not codactos:
            return Response({"error": "acto parameter is required."}, status=400)
        codactos_array = [codactos[i : i + 3] for i in range(0, len(codactos), 3)]
        templates = models.TplTemplate.objects.filter(codeacts__in=codactos_array)
        if not templates.exists():
            return Response([], status=200)

        serializer = serializers.TemplateSerializer(templates, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], url_path="upload")
    def upload_template(self, request):
        """
        Upload a template file to R2 '/plantillas' using nameTemplate as filename.
        - Expects multipart/form-data with:
          - file: .docx file
          - nameTemplate: string (used as base filename)
          - codeActs (optional): 3-char codes concatenated (e.g., '123456')
          - fkTypeKardex (optional): integer
        - Saves/updates a TplTemplate record with provided metadata.
        """
        return self._handle_template_upload(request)


class LegalizacionViewSet(ModelViewSet):
    """
    ViewSet for the Legalizacion model.
    """

    queryset = models.Legalizacion.objects.all().order_by("-idlegalizacion")
    serializer_class = serializers.LegalizacionSerializer
    pagination_class = pagination.KardexPagination

    def list(self, request, *args, **kwargs):
        dateFrom = request.query_params.get("dateFrom", "")
        dateTo = request.query_params.get("dateTo", "")

        print("dateFrom", dateFrom)
        print("dateTo", dateTo)

        if dateFrom and dateTo:
            self.queryset = self.queryset.filter(fechaingreso__range=(dateFrom, dateTo))
        elif dateFrom:
            self.queryset = self.queryset.filter(fechaingreso__gte=dateFrom)
        elif dateTo:
            self.queryset = self.queryset.filter(fechaingreso__lte=dateTo)

        return super().list(request, *args, **kwargs)


class PermiViajeViewSet(ModelViewSet):
    """
    ViewSet for the PermiViaje model.
    """

    queryset = models.PermiViaje.objects.all().order_by("-id_viaje")
    serializer_class = serializers.PermiViajeSerializer
    pagination_class = pagination.KardexPagination

    def get_serializer_class(self):
        if self.request.method in ["POST", "PUT", "PATCH"]:
            return serializers.CreatePermiViajeSerializer
        return serializers.PermiViajeSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a PermiViaje instance with auto-generated correlative numbers.
        Generates correlative numbers for num_kardex and num_formu fields.

        num_kardex format: "YYYYNNNNNN" (year + 6-digit correlative, resets yearly)
        num_formu format: "NNNNNNN" (7-digit correlative that increments)
        """
        data = request.data.copy()
        current_year = datetime.now().year

        # Single query to get the last record (using same ordering as queryset)
        try:
            # Get the last record by id_viaje (same as queryset ordering)
            last_record = (
                models.PermiViaje.objects.filter(num_formu__isnull=False)
                .exclude(num_formu="")
                .order_by("-id_viaje")
                .first()
            )

            if last_record and last_record.num_formu:
                # Generate num_formu: continue from last global value
                last_num_formu = int(last_record.num_formu)
                new_num_formu = last_num_formu + 1

                # Generate num_kardex: check if last record is from current year
                if last_record.num_kardex and last_record.num_kardex.startswith(str(current_year)):
                    # Same year, increment correlative
                    last_correlative = int(last_record.num_kardex[-6:])
                    new_correlative = last_correlative + 1
                else:
                    # New year, start with 000001
                    new_correlative = 1
            else:
                # First record ever, start with defaults
                new_num_formu = 1
                new_correlative = 1

            # Format the correlative numbers
            print("new_num_formu", new_num_formu)
            print("new_correlative", new_correlative)
            data["num_formu"] = f"{new_num_formu:07d}"
            data["num_kardex"] = f"{current_year}{new_correlative:06d}"

        except Exception as e:
            # Fallback values if there's an error
            data["num_formu"] = "0000001"
            data["num_kardex"] = f"{current_year}000001"

        # Create the serializer with the modified data
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def list(self, request, *args, **kwargs):

        # FILTERS - Apply filters BEFORE pagination
        # crono, tipoPermiso, nombreParticipante, numeroControl, dateFrom, dateTo
        crono = request.query_params.get("crono", None)
        tipoPermiso = request.query_params.get("tipoPermiso", None)
        nombreParticipante = request.query_params.get("nombreParticipante", None)
        numeroControl = request.query_params.get("numeroControl", None)
        dateFrom = request.query_params.get("dateFrom", None)
        dateTo = request.query_params.get("dateTo", None)

        # Apply filters to queryset
        if dateFrom and dateTo:
            self.queryset = self.queryset.filter(fec_ingreso__range=(dateFrom, dateTo))
        elif dateFrom:
            self.queryset = self.queryset.filter(fec_ingreso__gte=dateFrom)
        elif dateTo:
            self.queryset = self.queryset.filter(fec_ingreso__lte=dateTo)
        if crono:
            self.queryset = self.queryset.filter(num_kardex=crono)
        if tipoPermiso:
            self.queryset = self.queryset.filter(asunto=tipoPermiso)
        if nombreParticipante:
            # Filter PermiViaje by related ViajeContratantes field
            self.queryset = self.queryset.filter(
                id_viaje__in=models.ViajeContratantes.objects.filter(
                    c_descontrat__icontains=nombreParticipante
                ).values_list("id_viaje", flat=True)
            )
        if numeroControl:
            self.queryset = self.queryset.filter(num_formu=numeroControl)

        # Now paginate the filtered queryset
        page_viajes = self.paginate_queryset(self.queryset)

        # Get all contratantes for all viajes in the page
        viaje_ids = [viaje.id_viaje for viaje in page_viajes]
        contratantes_map = {}

        if viaje_ids:
            contratantes_queryset = models.ViajeContratantes.objects.filter(
                id_viaje__in=viaje_ids
            ).values("id_viaje", "id_contratante", "c_descontrat", "c_condicontrat")

            # Group contratantes by id_viaje
            for contratante in contratantes_queryset:
                id_viaje = contratante["id_viaje"]
                if id_viaje not in contratantes_map:
                    contratantes_map[id_viaje] = []
                contratantes_map[id_viaje].append(contratante)

        serializer = serializers.PermiViajeSerializer(
            page_viajes, context={"contratantes_map": contratantes_map}, many=True
        )
        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        kardex = request.query_params.get("kardex")
        nombreParticipante = request.query_params.get("nombreParticipante", None)

        if kardex:
            queryset = self.queryset.filter(num_kardex=kardex).first()
        else:
            return Response({"error": "kardex parameter is required."}, status=400)

        if not queryset:
            return Response({"error": "No viaje found for this kardex."}, status=404)

        if nombreParticipante:
            # Filter PermiViaje by related ViajeContratantes field
            self.queryset = self.queryset.filter(
                id_viaje__in=models.ViajeContratantes.objects.filter(
                    c_descontrat__icontains=nombreParticipante
                ).values_list("id_viaje", flat=True)
            )

        # Get all contratantes for all viajes in the page
        viaje_id = queryset.id_viaje
        contratantes_map = {}

        if viaje_id:
            contratantes_queryset = models.ViajeContratantes.objects.filter(
                id_viaje=viaje_id
            ).values("id_viaje", "id_contratante", "c_descontrat", "c_condicontrat")

            # Group contratantes by id_viaje
            for contratante in contratantes_queryset:
                id_viaje = contratante["id_viaje"]
                if id_viaje not in contratantes_map:
                    contratantes_map[id_viaje] = []
                contratantes_map[id_viaje].append(contratante)

        serializer = serializers.PermiViajeSerializer(
            queryset, context={"contratantes_map": contratantes_map}
        )
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="reporte")
    def reporte(self, request):
        """
        Generate chronological index report for permisos de viaje.

        Parameters:
        - fechade: Start date (DD/MM/YYYY)
        - fechaa: End date (DD/MM/YYYY)
        - tipo_documento: 'EXCEL' or 'WORD'
        """

        fechade = request.query_params.get("fechade")
        fechaa = request.query_params.get("fechaa")
        tipo_documento = request.query_params.get("tipo_documento", "WORD")

        if not fechade or not fechaa:
            return Response(
                {"error": "Both fechade and fechaa are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Convert dates from DD/MM/YYYY to YYYY-MM-DD
        try:
            desde = datetime.strptime(fechade, "%d/%m/%Y").strftime("%Y-%m-%d")
            hasta = datetime.strptime(fechaa, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use DD/MM/YYYY"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Generate report using the service
        report_service = PermisosViajeReportService()

        if tipo_documento == "EXCEL":
            return report_service.generate_excel_report(desde, hasta)
        else:
            return report_service.generate_word_report(desde, hasta)


class ViajeContratantesViewSet(ModelViewSet):
    """
    ViewSet for the ViajeContratantes model.
    """

    queryset = models.ViajeContratantes.objects.all()
    serializer_class = serializers.ViajeContratantesSerializer
    pagination_class = pagination.KardexPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return serializers.ViajeContratantesSerializer
        return serializers.ViajeContratantesSerializer

    @action(detail=False, methods=["get"])
    def by_viaje(self, request):
        """
        Get ViajeContratantes records by viaje.
        """
        id_viaje = request.query_params.get("id_viaje")
        if not id_viaje:
            return Response({"error": "id_viaje parameter is required."}, status=400)

        viaje_contratantes = models.ViajeContratantes.objects.filter(id_viaje=id_viaje)
        if not viaje_contratantes.exists():
            return Response([], status=200)

        serializer = serializers.ViajeContratantesSerializer(viaje_contratantes, many=True)
        return Response(serializer.data)


class IngresoPoderesViewSet(ModelViewSet):
    """
    ViewSet for the IngresoPoderes model.
    """

    queryset = models.IngresoPoderes.objects.all().order_by("-id_poder")
    serializer_class = serializers.IngresoPoderesSerializer
    pagination_class = pagination.KardexPagination

    def get_serializer_class(self):
        if self.request.method in ["POST", "PUT", "PATCH"]:
            return serializers.CreateIngresoPoderesSerializer
        return serializers.IngresoPoderesSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a IngresoPoderes instance with auto-generated correlative numbers.
        Generates correlative numbers for num_kardex and num_formu fields.

        num_kardex format: "YYYYNNNNNN" (year + 6-digit correlative, resets yearly)
        num_formu format: "NNNNNNN" (7-digit correlative that increments)
        """
        data = request.data.copy()
        current_year = datetime.now().year

        # Single query to get the last record (using same ordering as queryset)
        try:
            # Get the last record by id_poder (same as queryset ordering)
            last_record = (
                models.IngresoPoderes.objects.filter(num_formu__isnull=False)
                .exclude(num_formu="")
                .order_by("-id_poder")
                .first()
            )

            if last_record and last_record.num_formu:
                # Generate num_formu: continue from last global value
                last_num_formu = int(last_record.num_formu)
                new_num_formu = last_num_formu + 1

                # Generate num_kardex: check if last record is from current year
                if last_record.num_kardex and last_record.num_kardex.startswith(str(current_year)):
                    # Same year, increment correlative
                    last_correlative = int(last_record.num_kardex[-6:])
                    new_correlative = last_correlative + 1
                else:
                    # New year, start with 000001
                    new_correlative = 1
            else:
                # First record ever, start with defaults
                new_num_formu = 1
                new_correlative = 1

            # Format the correlative numbers
            data["num_formu"] = f"{new_num_formu:07d}"
            data["num_kardex"] = f"{current_year}{new_correlative:06d}"

        except Exception as e:
            # Fallback values if there's an error
            data["num_formu"] = "0000001"
            data["num_kardex"] = f"{current_year}000001"

        # Create the serializer with the modified data
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def list(self, request, *args, **kwargs):

        dateFrom = request.query_params.get("dateFrom", "")
        dateTo = request.query_params.get("dateTo", "")
        dateType = request.query_params.get("dateType", "")

        if dateType == "fecha_ingreso":
            if dateFrom and dateTo:
                # Convert string dates to proper format for string comparison
                self.queryset = self.queryset.filter(
                    fec_ingreso__gte=dateFrom, fec_ingreso__lte=dateTo
                )
            elif dateFrom:
                self.queryset = self.queryset.filter(fec_ingreso__gte=dateFrom)
            elif dateTo:
                self.queryset = self.queryset.filter(fec_ingreso__lte=dateTo)
        elif dateType == "fecha_crono":
            if dateFrom and dateTo:
                self.queryset = self.queryset.filter(fec_crono__range=(dateFrom, dateTo))
            elif dateFrom:
                self.queryset = self.queryset.filter(fec_crono__gte=dateFrom)
            elif dateTo:
                self.queryset = self.queryset.filter(fec_crono__lte=dateTo)
        elif dateType == "fecha_diligencia":
            if dateFrom and dateTo:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_entrega, '%%d/%%m/%%Y') BETWEEN STR_TO_DATE(%s, '%%d/%%m/%%Y') AND STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateFrom, dateTo],
                )
            elif dateFrom:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_entrega, '%%d/%%m/%%Y') >= STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateFrom],
                )
            elif dateTo:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_entrega, '%%d/%%m/%%Y') <= STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateTo],
                )

        page_permisos = self.paginate_queryset(self.queryset)

        permisos_ids = [permiso.id_poder for permiso in page_permisos]
        contratantes_map = {}

        if permisos_ids:
            contratantes_queryset = models.PoderesContratantes.objects.filter(
                id_poder__in=permisos_ids
            ).values("id_poder", "id_contrata", "c_descontrat", "c_condicontrat")

            for contratante in contratantes_queryset:
                id_poder = contratante["id_poder"]
                if id_poder not in contratantes_map:
                    contratantes_map[id_poder] = []
                contratantes_map[id_poder].append(contratante)

        serializer = serializers.IngresoPoderesSerializer(
            page_permisos, context={"contratantes_map": contratantes_map}, many=True
        )
        return self.get_paginated_response(serializer.data)


class PoderesFueraregViewSet(ModelViewSet):
    """
    ViewSet for the PoderesFuerareg model.
    """

    queryset = models.PoderesFuerareg.objects.all().order_by("-id_fuerareg")
    serializer_class = serializers.PoderesFueraregSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=["get"])
    def by_poder(self, request):
        """
        Get PoderesFuerareg records by poder.
        """
        id_poder = request.query_params.get("id_poder", None)
        if id_poder:
            queryset = models.PoderesFuerareg.objects.filter(id_poder=id_poder).first()
            if not queryset:
                return Response(status=status.HTTP_200_OK, data={})
            serializer = self.get_serializer(queryset)
            return Response(serializer.data)
        return Response(status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"], url_path="reporte")
    def reporte(self, request):
        # TEST THIS ENDPOINT
        """Generate poderes report (Excel or Word)"""
        from app.ducumentation.extraprotocolares.poderes import PoderesReportService
        from datetime import datetime

        fechade = request.query_params.get("fechade")
        fechaa = request.query_params.get("fechaa")
        tipo_documento = request.query_params.get("tipo_documento", "WORD")

        if not fechade or not fechaa:
            return Response(
                {"error": "Both fechade and fechaa are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Convert DD/MM/YYYY to YYYY-MM-DD
            desde = datetime.strptime(fechade, "%d/%m/%Y").strftime("%Y-%m-%d")
            hasta = datetime.strptime(fechaa, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use DD/MM/YYYY"}, status=status.HTTP_400_BAD_REQUEST
            )

        report_service = PoderesReportService()

        if tipo_documento == "EXCEL":
            return report_service.generate_excel_report(desde, hasta)
        else:
            return report_service.generate_word_report(desde, hasta)


class PoderesPensionViewSet(ModelViewSet):
    """
    ViewSet for the PoderesPension model.
    """

    queryset = models.PoderesPension.objects.all().order_by("-id_pension")
    serializer_class = serializers.PoderesPensionSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=["get"])
    def by_poder(self, request):
        """
        Get PoderesPension records by poder.
        """
        id_poder = request.query_params.get("id_poder", None)
        if id_poder:
            queryset = models.PoderesPension.objects.filter(id_poder=id_poder).first()
            if not queryset:
                return Response(status=status.HTTP_200_OK, data={})
            serializer = self.get_serializer(queryset)
            return Response(serializer.data)
        return Response(status=status.HTTP_400_BAD_REQUEST)


class PoderesContratantesViewSet(ModelViewSet):
    """
    ViewSet for the PoderesContratantes model.
    """

    queryset = models.PoderesContratantes.objects.all()
    serializer_class = serializers.PoderesContratantesSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=["get"])
    def by_poder(self, request):
        """
        Get PoderesContratantes records by poder.
        """
        id_poder = request.query_params.get("id_poder", None)
        if id_poder:
            queryset = models.PoderesContratantes.objects.filter(id_poder=id_poder)
            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)
        return Response(status=status.HTTP_400_BAD_REQUEST)


class IngresoCartasViewSet(ModelViewSet):
    """
    ViewSet for the IngresoCartas model.
    """

    queryset = models.IngresoCartas.objects.all().order_by("-id_carta")
    serializer_class = serializers.IngresoCartasSerializer
    pagination_class = pagination.KardexPagination
    permission_classes = [IsAuthenticated]

    def list(self, request, *args, **kwargs):

        numCarta = request.query_params.get("numCarta", "")
        remitente = request.query_params.get("remitente", "")
        destinatario = request.query_params.get("destinatario", "")
        dateFrom = request.query_params.get("dateFrom", "")
        dateTo = request.query_params.get("dateTo", "")
        dateType = request.query_params.get("dateType", "")
        if dateType == "fecha_ingreso":
            if dateFrom and dateTo:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_ingreso, '%%d/%%m/%%Y') BETWEEN STR_TO_DATE(%s, '%%d/%%m/%%Y') AND STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateFrom, dateTo],
                )
            elif dateFrom:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_ingreso, '%%d/%%m/%%Y') >= STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateFrom],
                )
            elif dateTo:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_ingreso, '%%d/%%m/%%Y') <= STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateTo],
                )
        elif dateType == "fecha_diligencia":
            if dateFrom and dateTo:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_entrega, '%%d/%%m/%%Y') BETWEEN STR_TO_DATE(%s, '%%d/%%m/%%Y') AND STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateFrom, dateTo],
                )
            elif dateFrom:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_entrega, '%%d/%%m/%%Y') >= STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateFrom],
                )
            elif dateTo:
                self.queryset = self.queryset.extra(
                    where=[
                        "STR_TO_DATE(fec_entrega, '%%d/%%m/%%Y') <= STR_TO_DATE(%s, '%%d/%%m/%%Y')"
                    ],
                    params=[dateTo],
                )

        if numCarta:
            self.queryset = self.queryset.filter(num_carta=numCarta)
        if remitente:
            # Normalize input: strip whitespace and handle common variations
            normalized_remitente = remitente.strip()
            self.queryset = self.queryset.filter(nom_remitente__icontains=normalized_remitente)
        if destinatario:
            # Normalize input: strip whitespace and handle common variations
            normalized_destinatario = destinatario.strip()
            self.queryset = self.queryset.filter(
                nom_destinatario__icontains=normalized_destinatario
            )

        page_cartas = self.paginate_queryset(self.queryset)

        serializer = serializers.IngresoCartasSerializer(page_cartas, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Create a IngresoCartas instance with auto-generated correlative numbers.
        Generates correlative numbers for num_carta field.

        num_carta format: "YYYYNNNNNN" (year + 6-digit correlative, resets yearly)
        """
        data = request.data.copy()
        current_year = datetime.now().year

        try:
            # Get the last record by id_carta (same as queryset ordering)
            last_record = (
                models.IngresoCartas.objects.filter(num_carta__isnull=False)
                .exclude(num_carta="")
                .order_by("-id_carta")
                .first()
            )

            if last_record and last_record.num_carta:
                # Generate num_carta: check if last record is from current year
                if last_record.num_carta and last_record.num_carta.startswith(str(current_year)):
                    # Same year, increment correlative
                    last_correlative = int(last_record.num_carta[-6:])
                    new_correlative = last_correlative + 1
                else:
                    # New year, start with 000001
                    new_correlative = 1
            else:
                # First record ever, start with defaults
                new_correlative = 1

            # Format the correlative number
            data["num_carta"] = f"{current_year}{new_correlative:06d}"

        except Exception as e:
            # Fallback values if there's an error
            data["num_carta"] = f"{current_year}000001"

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=["get"], url_path="reporte")
    def reporte(self, request):
        """
        Generate chronological index report for cartas notariales.

        Parameters:
        - fechade: Start date (DD/MM/YYYY)
        - fechaa: End date (DD/MM/YYYY)
        - tipo_documento: 'EXCEL' or 'WORD'
        """
        fechade = request.query_params.get(
            "fechade"
        )  # Changed from request.data to request.query_params
        fechaa = request.query_params.get("fechaa")
        tipo_documento = request.query_params.get("tipo_documento", "WORD")

        if not fechade or not fechaa:
            return Response(
                {"error": "Both fechade and fechaa are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Convert dates from DD/MM/YYYY to YYYY-MM-DD
        try:
            desde = datetime.strptime(fechade, "%d/%m/%Y").strftime("%Y-%m-%d")
            hasta = datetime.strptime(fechaa, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use DD/MM/YYYY"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Generate report using your service
        report_service = CartasNotarialesReportService()

        if tipo_documento == "EXCEL":
            return report_service.generate_excel_report(desde, hasta)
        else:
            return report_service.generate_word_report(desde, hasta)


class SellosViewSet(ModelViewSet):

    queryset = models.Selloscartas.objects.all()
    serializer_class = serializers.SelloscartasSerializer
    permission_classes = [IsAuthenticated]


class LibrosViewSet(ModelViewSet):
    """
    ViewSet for the Libros model.
    """

    queryset = models.Libros.objects.all().order_by("-id")
    serializer_class = serializers.LibrosSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=["get"], url_path="reporte")
    def reporte(self, request):
        """
        Generate chronological index report for libros.

        Parameters:
        - fechade: Start date (DD/MM/YYYY)
        - fechaa: End date (DD/MM/YYYY)
        - tipo_documento: 'EXCEL' or 'WORD'
        - orientation: 'vertical' or 'horizontal' (default: 'horizontal')
        """
        from ducumentation.extraprotocolares.libros import LibrosReportService
        from datetime import datetime

        fechade = request.query_params.get("fechade")
        fechaa = request.query_params.get("fechaa")
        tipo_documento = request.query_params.get("tipo_documento", "WORD")
        orientation = request.query_params.get("orientation", "horizontal")
        # print('orientation', orientation)

        if not fechade or not fechaa:
            return Response(
                {"error": "Both fechade and fechaa are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate date format but keep original format for the service
        try:
            # Just validate the format
            datetime.strptime(fechade, "%d/%m/%Y")
            datetime.strptime(fechaa, "%d/%m/%Y")
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use DD/MM/YYYY"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Generate report using the service
        report_service = LibrosReportService()

        if tipo_documento == "EXCEL":
            return report_service.generate_excel_report(fechade, fechaa)
        else:
            return report_service.generate_word_report(fechade, fechaa, orientation)

    @action(detail=False, methods=["get"], url_path="by_numlibro")
    def by_numlibro(self, request):
        """
        Get libros by numlibro.
        """
        numlibro = request.query_params.get("numlibro", "")
        if not numlibro:
            return Response({"error": "numlibro is required"}, status=status.HTTP_400_BAD_REQUEST)
        libro = self.queryset.filter(numlibro=numlibro).first()
        if not libro:
            return Response({"error": "libro not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(libro)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        dateFrom = request.query_params.get("dateFrom", "")
        dateTo = request.query_params.get("dateTo", "")
        empresa = request.query_params.get("empresa", "")
        document = request.query_params.get("document", "")
        num_libro = request.query_params.get("num_libro", "")
        year = request.query_params.get("year", "")

        if dateFrom and dateTo:
            self.queryset = self.queryset.filter(fecing__range=(dateFrom, dateTo))
        elif dateFrom:
            self.queryset = self.queryset.filter(fecing__gte=dateFrom)
        elif dateTo:
            self.queryset = self.queryset.filter(fecing__lte=dateTo)

        if empresa:
            self.queryset = self.queryset.filter(empresa=empresa)
        if document:
            self.queryset = self.queryset.filter(ruc=document)
        if num_libro and year:
            self.queryset = self.queryset.filter(numlibro=num_libro, ano=year)

        page_libros = self.paginate_queryset(self.queryset)
        serializer = serializers.LibrosSerializer(page_libros, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Create a Libros instance with auto-generated correlative numbers.
        Generates correlative numbers for numlibro field.
        """
        data = request.data.copy()
        last_record = (
            models.Libros.objects.filter(numlibro__isnull=False)
            .exclude(numlibro="")
            .order_by("-id")
            .first()
        )

        if last_record and last_record.numlibro:
            last_correlative = int(last_record.numlibro[-6:])
            new_correlative = last_correlative + 1
        else:
            new_correlative = 1

        data["numlibro"] = f"{new_correlative:06d}"

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=["get"], url_path="pdt-errors")
    def pdt_errors(self, request):
        """
        Get PDT errors for libros in a date range.

        Parameters:
        - initialDate: Start date (DD/MM/YYYY)
        - finalDate: End date (DD/MM/YYYY)
        - page: Page number (default: 1)
        - page_size: Number of items per page (default: 10)
        """
        try:
            # Get and validate parameters
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")

            if not initial_date or not final_date:
                return Response(
                    {"error": "Both initialDate and finalDate are required (DD/MM/YYYY format)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Process PDT errors
            pdt_service = PdtLibrosService(initial_date, final_date)
            pdt_service.load_data()
            results = pdt_service.get_results()

            # Return results
            if request.accepted_renderer.format == "html":
                # Return HTML view
                from django.template.response import TemplateResponse

                return TemplateResponse(
                    request,
                    "pdt_libros_errors.html",
                    {
                        "initial_date": initial_date,
                        "final_date": final_date,
                        "total_libros": results["totalRecords"],
                        "total_errors": results["totalError"],
                        "errors": results["list"],
                    },
                )
            else:
                # Paginate the results
                from rest_framework.pagination import PageNumberPagination

                paginator = PageNumberPagination()
                paginator.page_size = int(request.query_params.get("page_size", 10))
                paginated_errors = paginator.paginate_queryset(results["list"], request)

                # Return paginated JSON response
                return Response(
                    {
                        "count": len(results["list"]),
                        "total_pages": (len(results["list"]) + paginator.page_size - 1)
                        // paginator.page_size,
                        "current_page": int(request.query_params.get("page", 1)),
                        "page_size": paginator.page_size,
                        "results": paginated_errors,
                        "summary": results["summary"],
                    }
                )

        except Exception as e:
            logger.error(f"Error processing PDT errors: {str(e)}", exc_info=True)
            return Response(
                {"error": "Error processing PDT errors", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=False, methods=["get"], url_path="download-pdt")
    def download_pdt_file(self, request):
        """
        Download PDT file for libros.

        Parameters:
        - initialDate: Start date (DD/MM/YYYY)
        - finalDate: End date (DD/MM/YYYY)
        """
        try:
            # Get and validate parameters
            initial_date = request.query_params.get("initialDate")
            final_date = request.query_params.get("finalDate")

            if not initial_date or not final_date:
                return Response(
                    {"error": "Both initialDate and finalDate are required (DD/MM/YYYY format)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Generate PDT file
            pdt_service = PdtFileService(
                initial_date=initial_date,
                final_date=final_date,
                file_type=PdtFileService.FILE_TYPE_LIB,
            )

            return pdt_service.generate_file()

        except Exception as e:
            logger.error(f"Error generating PDT file: {str(e)}", exc_info=True)
            return Response(
                {"error": "Error generating PDT file", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TipolibroViewSet(ModelViewSet):
    """
    ViewSet for the Tipolibro model.
    """

    queryset = models.Tipolibro.objects.all()
    serializer_class = serializers.TipolibroSerializer


class CertDomiciliarioViewSet(ModelViewSet):
    """
    ViewSet for the CertDomiciliario model.
    """

    queryset = models.CertDomiciliario.objects.all().order_by("-id_domiciliario")
    serializer_class = serializers.CertDomiciliarioSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=["get"], url_path="reporte")
    def reporte(self, request):
        """
        Generate chronological index report for cert_domiciliario.
        Parameters:
        - fechade: Start date (DD/MM/YYYY)
        - fechaa: End date (DD/MM/YYYY)
        - tipo_documento: 'EXCEL' or 'WORD'
        - orientation: 'vertical' or 'horizontal' (default: 'horizontal')
        """

        fechade = request.query_params.get("fechade")
        fechaa = request.query_params.get("fechaa")
        tipo_documento = request.query_params.get("tipo_documento", "WORD")
        orientation = request.query_params.get("orientation", "horizontal")

        if not fechade or not fechaa:
            return Response(
                {"error": "Both fechade and fechaa are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Convert dates from DD/MM/YYYY to YYYY-MM-DD
        try:
            desde = datetime.strptime(fechade, "%d/%m/%Y").strftime("%Y-%m-%d")
            hasta = datetime.strptime(fechaa, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use DD/MM/YYYY"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validate orientation
        if orientation not in ["vertical", "horizontal"]:
            return Response(
                {"error": 'Invalid orientation. Use "vertical" or "horizontal"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        report_service = CertDomiciliariosReportService()

        if tipo_documento == "EXCEL":
            return report_service.generate_excel_report(desde, hasta, orientation=orientation)
        else:
            return report_service.generate_word_report(desde, hasta, orientation=orientation)

    def list(self, request, *args, **kwargs):
        dateFrom = request.query_params.get("dateFrom", "")
        dateTo = request.query_params.get("dateTo", "")
        num_certificado = request.query_params.get("num_certificado", "")
        nombre_solic = request.query_params.get("nombre_solic", "")

        if dateFrom and dateTo:
            self.queryset = self.queryset.filter(fec_ingreso__range=(dateFrom, dateTo))
        elif dateFrom:
            self.queryset = self.queryset.filter(fec_ingreso__gte=dateFrom)
        elif dateTo:
            self.queryset = self.queryset.filter(fec_ingreso__lte=dateTo)

        if num_certificado:

            self.queryset = self.queryset.filter(num_certificado=num_certificado)
        if nombre_solic:
            self.queryset = self.queryset.filter(nombre_solic__icontains=nombre_solic)

        page_cert_domiciliario = self.paginate_queryset(self.queryset)
        serializer = serializers.CertDomiciliarioSerializer(page_cert_domiciliario, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        Create a CertDomiciliario instance with auto-generated correlative numbers.
        Generates correlative numbers for num_certificado field.

        num_certificado format: "YYYYNNNNNN" (year + 6-digit correlative, resets yearly)
        """
        data = request.data.copy()
        current_year = datetime.now().year

        try:
            # Get the last record by id_domiciliario (same as queryset ordering)
            last_record = (
                models.CertDomiciliario.objects.filter(num_certificado__isnull=False)
                .exclude(num_certificado="")
                .order_by("-id_domiciliario")
                .first()
            )

            if last_record and last_record.num_certificado:
                # Generate num_certificado: check if last record is from current year
                if last_record.num_certificado and last_record.num_certificado.startswith(
                    str(current_year)
                ):
                    # Same year, increment correlative
                    last_correlative = int(last_record.num_certificado[-6:])
                    new_correlative = last_correlative + 1
                else:
                    # New year, start with 000001
                    new_correlative = 1
            else:
                # First record ever, start with defaults
                new_correlative = 1

            # Format the correlative number
            data["num_certificado"] = f"{current_year}{new_correlative:06d}"

        except Exception as e:
            # Fallback values if there's an error
            data["num_certificado"] = f"{current_year}000001"

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class RentaViewSet(ModelViewSet):
    """
    ViewSet for the Renta model.
    """

    queryset = models.Renta.objects.all()
    serializer_class = serializers.RentaSerializer
    pagination_class = pagination.KardexPagination

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create or update a Renta instance with auto-generated correlative numbers.
        Generates correlative numbers for idrenta field.
        Implements the same logic as the PHP script.
        """
        data = request.data.copy()

        # Extract required fields
        idcontratante = data.get("idcontratante")
        kardex = data.get("kardex")
        pregu1 = data.get("pregu1")
        pregu2 = data.get("pregu2")
        pregu3 = data.get("pregu3")

        if not all([idcontratante, kardex, pregu1, pregu2, pregu3]):
            return Response(
                {"error": "Missing required fields: idcontratante, kardex, pregu1, pregu2, pregu3"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Pad idcontratante with zeros to make it 10 digits
            idcontratante_padded = str(idcontratante).zfill(10)

            # Check if record already exists for this kardex and idcontratante (like PHP script)
            existing_renta = models.Renta.objects.filter(
                kardex=kardex, idcontratante=idcontratante_padded
            ).first()

            if existing_renta:
                # Update existing record (like PHP script)
                existing_renta.pregu1 = pregu1
                existing_renta.pregu2 = pregu2
                existing_renta.pregu3 = pregu3
                existing_renta.save()

                # Serialize the updated record
                serializer = self.get_serializer(existing_renta)

                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                # Get the last record to generate new idrenta (like PHP script)
                last_record = models.Renta.objects.order_by("-idrenta").first()

                if last_record and last_record.idrenta:
                    # Convert to int, increment, then pad with zeros
                    numero = int(last_record.idrenta)
                    suma = numero + 1
                    cantidad = len(str(suma))

                    # Pad with zeros to make it 6 digits (like PHP switch statement)
                    if cantidad == 1:
                        nrenta = f"00000{suma}"
                    elif cantidad == 2:
                        nrenta = f"0000{suma}"
                    elif cantidad == 3:
                        nrenta = f"000{suma}"
                    elif cantidad == 4:
                        nrenta = f"00{suma}"
                    elif cantidad == 5:
                        nrenta = f"0{suma}"
                    elif cantidad == 6:
                        nrenta = str(suma)
                    else:
                        nrenta = str(suma).zfill(6)  # Fallback for longer numbers
                else:
                    # First record ever
                    nrenta = "000001"

                # Create new record (like PHP script)
                data["idrenta"] = nrenta
                data["idcontratante"] = idcontratante_padded  # Use padded idcontratante

                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)

                return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": f"Error processing renta: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FormularioViewSet(ModelViewSet):
    """
    ViewSet for the Formulario model.
    """

    queryset = models.Formulario.objects.all()
    serializer_class = serializers.FormularioSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=["get"])
    def by_renta(self, request):
        """
        Get all Formulario instances by renta.
        """
        idrenta = request.query_params.get("idrenta")
        if not idrenta:
            return Response({"error": "idrenta is required"}, status=status.HTTP_400_BAD_REQUEST)

        formulario = models.Formulario.objects.filter(idrenta=idrenta)
        serializer = serializers.FormularioSerializer(formulario, many=True)
        return Response(serializer.data)


class ConfinotarioViewSet(ModelViewSet):
    """
    ViewSet for the Confinotario model.
    """

    queryset = models.Confinotario.objects.all()
    serializer_class = serializers.ConfinotarioSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        """
        Return singleton notary config object (not an array).
        """
        instance = self.get_queryset().first()
        if not instance:
            return Response({}, status=status.HTTP_200_OK)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def _ensure_superuser(self, request):
        if not request.user or not request.user.is_authenticated or not request.user.is_superuser:
            return Response(
                {"detail": "Usuario no autorizado para modificar la configuración del notario."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def update(self, request, *args, **kwargs):
        denied = self._ensure_superuser(request)
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        denied = self._ensure_superuser(request)
        if denied:
            return denied
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        denied = self._ensure_superuser(request)
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)


class TiposdeactoViewSet(ModelViewSet):
    """
    ViewSet for the Tiposdeacto model.

    List is paginated (see KardexPagination: ``page``, ``page_size`` query params).

    Optional query filters for ``GET`` list:

    - ``desacto`` — substring match (case-insensitive) on ``desacto``
    - ``idtipoacto`` — exact match on ``idtipoacto``
    - ``idtipkar`` — exact match on ``idtipkar`` (integer)

    ``POST`` (create): ``idtipoacto`` is auto-generated (max numeric id + 1, as legacy PHP).
    ``indicador`` and ``rol_part`` are normalized to uppercase on save.
    ``codigo_visual`` / ``codigoVisual`` is trimmed and stored as ``""`` when empty (not NULL).
    """

    queryset = models.Tiposdeacto.objects.all().order_by("idtipoacto")
    serializer_class = serializers.TiposdeactoSerializer
    pagination_class = pagination.KardexPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action != "list":
            return qs
        p = self.request.query_params
        desacto = p.get("desacto")
        if desacto:
            qs = qs.filter(desacto__icontains=desacto.strip())
        idtipoacto = p.get("idtipoacto")
        if idtipoacto is not None and idtipoacto != "":
            qs = qs.filter(idtipoacto=idtipoacto.strip())
        idtipkar = p.get("idtipkar")
        if idtipkar is not None and idtipkar != "":
            try:
                qs = qs.filter(idtipkar=int(idtipkar))
            except (TypeError, ValueError):
                qs = qs.none()
        return qs
