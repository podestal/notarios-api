"""
Compliance cache API — Option B snapshots (UIF + SISGEN).
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notaria import pagination
from uif.services.date_utils import parse_date_range

from compliance.services.dashboard_service import (
    ComplianceDashboardService,
    parse_idtipkar_list,
)
from compliance.services.payload import SUPPORTED_SOURCES, serialize_cache_row
from compliance.services.refresh_service import ComplianceRefreshService

logger = logging.getLogger(__name__)


class ComplianceDashboardView(APIView):
    """
    Paginated compliance snapshots per kardex.

    Query params:
      - initialDate, finalDate (DD/MM/YYYY or YYYY-MM-DD) — filter by fechaescritura
      - idtipkar — comma-separated (e.g. 1,3,4)
      - source — uif | sisgen (filters kardex with errors in that source)
      - hasErrors — true (default) | false | all
      - includePayload — true (default) | false
      - page, page_size
    """

    permission_classes = [IsAuthenticated]
    pagination_class = pagination.KardexPagination

    def get(self, request):
        initial_date = request.query_params.get("initialDate")
        final_date = request.query_params.get("finalDate")
        source = (request.query_params.get("source") or "").strip().lower() or None
        if source and source not in SUPPORTED_SOURCES:
            return Response(
                {
                    "error": "Invalid source. Use: uif, sisgen (pdt coming soon)",
                    "supported_sources": sorted(SUPPORTED_SOURCES),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_errors_param = (request.query_params.get("hasErrors") or "true").strip().lower()
        if has_errors_param == "all":
            has_errors = None
        elif has_errors_param in ("false", "0", "no"):
            has_errors = False
        else:
            has_errors = True

        include_payload = (
            request.query_params.get("includePayload", "true").strip().lower() != "false"
        )

        start_date = end_date = None
        if initial_date or final_date:
            if not initial_date or not final_date:
                return Response(
                    {"error": "Both initialDate and finalDate are required when filtering by date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            parsed = parse_date_range(initial_date, final_date)
            if isinstance(parsed, Response):
                return parsed
            start_date, end_date = parsed

        idtipkar_list = parse_idtipkar_list(request.query_params.get("idtipkar"))

        service = ComplianceDashboardService()
        qs = service.build_list_queryset(
            start_date=start_date,
            end_date=end_date,
            idtipkar_list=idtipkar_list or None,
            source=source,
            has_errors=has_errors,
        )

        filters_meta = {
            "initialDate": initial_date,
            "finalDate": final_date,
            "idtipkar": request.query_params.get("idtipkar"),
            "source": source,
            "hasErrors": has_errors_param,
            "includePayload": include_payload,
        }

        paginator = self.pagination_class()

        def paginate_fn(queryset):
            return paginator.paginate_queryset(queryset, request, view=self)

        def get_paginated_response_fn(data):
            return paginator.get_paginated_response(data)

        return service.paginate_response(
            qs,
            paginate_fn=paginate_fn,
            get_paginated_response_fn=get_paginated_response_fn,
            source_filter=source,
            include_payload=include_payload,
            filters_meta=filters_meta,
        )


class ComplianceOverviewView(APIView):
    """
    Summary counts for home dashboard widgets (same filters as list, no pagination).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        initial_date = request.query_params.get("initialDate")
        final_date = request.query_params.get("finalDate")
        source = (request.query_params.get("source") or "").strip().lower() or None

        start_date = end_date = None
        if initial_date and final_date:
            parsed = parse_date_range(initial_date, final_date)
            if isinstance(parsed, Response):
                return parsed
            start_date, end_date = parsed
        elif initial_date or final_date:
            return Response(
                {"error": "Both initialDate and finalDate are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        idtipkar_list = parse_idtipkar_list(request.query_params.get("idtipkar"))
        service = ComplianceDashboardService()
        qs = service.build_list_queryset(
            start_date=start_date,
            end_date=end_date,
            idtipkar_list=idtipkar_list or None,
            source=source,
            has_errors=True,
        )
        summary = service.aggregate_summary(
            qs,
            filters_meta={
                "initialDate": initial_date,
                "finalDate": final_date,
                "idtipkar": request.query_params.get("idtipkar"),
                "source": source,
            },
        )
        return Response({"summary": summary}, status=status.HTTP_200_OK)


class ComplianceRefreshView(APIView):
    """
    Refresh cached compliance JSON for one kardex or a date range.

    POST body:
      { "kardex": "K1-2026" }
      or
      { "initialDate": "01/04/2026", "finalDate": "30/04/2026" }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        service = ComplianceRefreshService()
        kardex = str(request.data.get("kardex", "")).strip()
        initial_date = request.data.get("initialDate")
        final_date = request.data.get("finalDate")

        if kardex:
            row = service.refresh_kardex(kardex, user=request.user)
            if not row:
                return Response(
                    {"error": f"Kardex not found: {kardex}"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(
                {
                    "refreshed": 1,
                    "kardex": row.kardex,
                    "has_errors": row.has_errors,
                    "counts": {
                        "uif": row.uif_error_count,
                        "sisgen": row.sisgen_error_count,
                        "total": row.total_error_count,
                    },
                    "item": serialize_cache_row(row, include_payload=True),
                },
                status=status.HTTP_200_OK,
            )

        if initial_date and final_date:
            parsed = parse_date_range(initial_date, final_date)
            if isinstance(parsed, Response):
                return parsed
            start_date, end_date = parsed
            result = service.refresh_date_range(
                start_date, end_date, user=request.user
            )
            return Response(result, status=status.HTTP_200_OK)

        return Response(
            {
                "error": "Provide kardex or initialDate + finalDate",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class ComplianceDetailView(APIView):
    """GET single kardex cache by kardex number."""

    permission_classes = [IsAuthenticated]

    def get(self, request, kardex: str):
        from compliance.models import KardexComplianceCache

        source = (request.query_params.get("source") or "").strip().lower() or None
        row = KardexComplianceCache.objects.filter(kardex=kardex).first()
        if not row:
            return Response(
                {"error": "No compliance cache for this kardex. POST /compliance/refresh/ first."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(
            serialize_cache_row(row, include_payload=True, source_filter=source),
            status=status.HTTP_200_OK,
        )
