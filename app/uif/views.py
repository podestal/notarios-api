"""
UIF module API views (Phase 4: dashboard, corrections, reports).
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notaria import pagination
from uif.services.corrections import UifCorrectionService
from uif.services.dashboard_service import UifDashboardService
from uif.services.report_data import parse_report_dates
from uif.services.reports import UifReportService

logger = logging.getLogger(__name__)


class UifErrorsDashboardView(APIView):
    """
    UIF error dashboard — loadData, generateData threshold, ro_validation_by_act.

    Query params: initialDate, finalDate, type (errors|ro|no_envian), page, page_size.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = pagination.KardexPagination

    def get(self, request):
        paginator = self.pagination_class()
        service = UifDashboardService()

        def paginate_fn(queryset):
            return paginator.paginate_queryset(queryset, request, view=self)

        def get_paginated_response_fn(data):
            return paginator.get_paginated_response(data)

        return service.build_response(request, paginate_fn, get_paginated_response_fn)


class UifErrorsCorrectView(APIView):
    """
    Subsanar errores UIF (subset of correct_error_uif.php).

    POST body: { "corrections": [ { kardex, codacto, fieldNumber, ... }, ... ] }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        corrections = request.data.get("corrections")
        if not isinstance(corrections, list) or not corrections:
            return Response(
                {"error": "Se requiere un arreglo 'corrections' con al menos un elemento"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = UifCorrectionService().apply(corrections)
        return Response(result, status=status.HTTP_200_OK)


class UifReportExcelView(APIView):
    """
    Excel UIF report — uses the same pipeline as /uif/errors/ (lista_kardex_ro).

    Query params: initialDate, finalDate (DD/MM/YYYY or YYYY-MM-DD).
    reportPolicy: all (default, PHP _arrObjRo) | clean (zero field errors only).
    """

    # permission_classes = [IsAuthenticated]

    def get(self, request):
        initial_date = request.query_params.get("initialDate")
        final_date = request.query_params.get("finalDate")
        report_policy = request.query_params.get("reportPolicy", "all")
        if not initial_date or not final_date:
            return Response(
                {"error": "Both initialDate and finalDate are required (DD/MM/YYYY format)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            parse_report_dates(initial_date, final_date)
            service = UifReportService()
            data = service.build_report_data(
                initial_date, final_date, report_policy=report_policy
            )
            return service.generate_excel_report(data, initial_date, final_date)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error("UIF Excel report failed: %s", exc, exc_info=True)
            return Response(
                {"error": "Error generating UIF report Excel", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UifReportPlaneView(APIView):
    """
    Plane file (archivo plano UIF).

    Query params: initialDate, finalDate.
    reportPolicy: all (default) | clean.
    responseFormat=json (default, legacy) | file (direct download).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        initial_date = request.query_params.get("initialDate")
        final_date = request.query_params.get("finalDate")
        report_policy = request.query_params.get("reportPolicy", "all")
        response_format = (request.query_params.get("responseFormat") or "json").lower()

        if not initial_date or not final_date:
            return Response(
                {"error": "Both initialDate and finalDate are required (DD/MM/YYYY format)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            parse_report_dates(initial_date, final_date)
            service = UifReportService()
            data = service.build_report_data(
                initial_date, final_date, report_policy=report_policy
            )

            if response_format == "file":
                return service.generate_plane_report(data, initial_date, final_date)

            payload = service.generate_plane_report_json(data, initial_date, final_date)
            payload["summary"] = data.get("summary", {})
            payload["report_policy"] = data.get("report_policy", "all")
            payload["records_in_report"] = len(service._report_records(data))
            return Response(payload, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error("UIF plane report failed: %s", exc, exc_info=True)
            return Response(
                {"error": "Error generating UIF plane report", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
