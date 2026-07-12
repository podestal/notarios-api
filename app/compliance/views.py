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
from compliance.services.kardex_detail_service import (
    ComplianceCacheNotFoundError,
    KardexComplianceDetailService,
    KardexNotFoundError,
)
from compliance.services.access import resolve_idusuario
from compliance.services.user_monthly_service import ComplianceUserMonthlyService

logger = logging.getLogger(__name__)


class ComplianceUsersMonthlyView(APIView):
    """
    Error counts by preparer (kardex.idusuario) for a calendar month.

    GET /compliance/users/
      - year (optional, default: current server year)
      - month (optional, default: current server month, 1–12)

    UIF counts use the same engine as the UIF report (``fechaescritura``, threshold,
    complementary tipo C). SISGEN uses cache/live; sisgen-sent / pending escritura
    skip SISGEN only. Kardex filtered by ``fechaescritura`` in the calendar month.

    Add ``cache=true`` to read SISGEN from cache only (UIF still from dashboard).
    Add ``live=true`` to force full SISGEN live validation.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params, err = _parse_users_month_params(request)
        if err is not None:
            return err

        service = ComplianceUserMonthlyService()
        try:
            report = service.build_report(
                year=params["year"],
                month=params["month"],
                use_cache=params["use_cache"],
                force_live=params["force_live"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(report, status=status.HTTP_200_OK)


def _parse_users_month_params(request):
    year_raw = request.query_params.get("year")
    month_raw = request.query_params.get("month")
    use_cache = request.query_params.get("cache", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    errors_only = request.query_params.get("errorsOnly", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    force_live = request.query_params.get("live", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        year = int(year_raw) if year_raw not in (None, "") else None
        month = int(month_raw) if month_raw not in (None, "") else None
    except ValueError:
        return None, Response(
            {"error": "year and month must be integers"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return {
        "year": year,
        "month": month,
        "use_cache": use_cache,
        "errors_only": errors_only,
        "force_live": force_live,
    }, None


def _user_kardex_report_response(report: dict) -> Response:
    """Flatten single-user block from ``build_user_kardex_report``."""
    if not report["users"]:
        return Response(
            {
                **report,
                "user": None,
                "total_kardex": 0,
                "kardex_with_errors": 0,
                "error_rate": 0.0,
                "kardex": [],
                "kardex_count": 0,
                "counts": {"sisgen": 0, "uif": 0, "pdt": 0, "total": 0},
            },
            status=status.HTTP_200_OK,
        )

    user_block = report["users"][0]
    return Response(
        {
            **report,
            "user": {
                "idusuario": user_block["idusuario"],
                "name": user_block["name"],
                "username": user_block["username"],
            },
            "total_kardex": user_block["total_kardex"],
            "kardex_with_errors": user_block["kardex_with_errors"],
            "error_rate": user_block["error_rate"],
            "kardex_count": user_block["kardex_count"],
            "counts": user_block["counts"],
            "kardex": user_block["kardex"],
        },
        status=status.HTTP_200_OK,
    )


class ComplianceMyKardexView(APIView):
    """
    Logged-in preparer's kardex list with compliance error counts.

    GET /compliance/me/kardex/
      - year, month (optional; default current month) — focus month
      - cache=true (optional) — cache only, no live fallback
      - live=true (optional) — force full live validation
      - errorsOnly=true (default) | false

    Always includes the focus month plus the previous two months in ``months``
    (newest first). Top-level ``kardex`` / ``counts`` stay the focus month for
    backward compatibility. ``rolling_summary`` aggregates all three months.

    ``idusuario`` is taken from the JWT user — never from query params.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params, err = _parse_users_month_params(request)
        if err is not None:
            return err

        service = ComplianceUserMonthlyService()
        try:
            report = service.build_my_kardex_rolling_report(
                year=params["year"],
                month=params["month"],
                use_cache=params["use_cache"],
                force_live=params["force_live"],
                idusuario=resolve_idusuario(request.user),
                errors_only=params["errors_only"],
                months_back=2,
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(report, status=status.HTTP_200_OK)


class ComplianceMyKardexErrorsView(APIView):
    """
    Full error detail for one kardex owned by the logged-in preparer.

    GET /compliance/me/kardex/<kardex>/errors/
      - cache=true (optional)
      - source=uif|sisgen (optional)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, kardex: str):
        use_cache = request.query_params.get("cache", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        source = (request.query_params.get("source") or "").strip().lower() or None
        if source and source not in SUPPORTED_SOURCES:
            return Response(
                {
                    "error": "Invalid source. Use: uif, sisgen",
                    "supported_sources": sorted(SUPPORTED_SOURCES),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = KardexComplianceDetailService()
        try:
            detail = service.build_detail_for_user(
                request.user,
                kardex,
                use_cache=use_cache,
                source_filter=source,
            )
        except KardexNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ComplianceCacheNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response(detail, status=status.HTTP_200_OK)


class ComplianceUsersKardexView(APIView):
    """
    Kardex with error counts grouped by preparer (counts only, no error payloads).

    GET /compliance/users/kardex/
      - year, month (optional; default current month)
      - cache=true (optional)
      - errorsOnly=true (default) | false
      - idusuario (optional; filter one user)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        params, err = _parse_users_month_params(request)
        if err is not None:
            return err

        idusuario_raw = request.query_params.get("idusuario")
        idusuario = None
        if idusuario_raw not in (None, ""):
            try:
                idusuario = int(idusuario_raw)
            except ValueError:
                return Response(
                    {"error": "idusuario must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        service = ComplianceUserMonthlyService()
        try:
            report = service.build_user_kardex_report(
                year=params["year"],
                month=params["month"],
                use_cache=params["use_cache"],
                force_live=params["force_live"],
                idusuario=idusuario,
                errors_only=params["errors_only"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(report, status=status.HTTP_200_OK)


class ComplianceUserKardexView(APIView):
    """
    Kardex with error counts for one preparer.

    GET /compliance/users/<idusuario>/kardex/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, idusuario: int):
        params, err = _parse_users_month_params(request)
        if err is not None:
            return err

        service = ComplianceUserMonthlyService()
        try:
            report = service.build_user_kardex_report(
                year=params["year"],
                month=params["month"],
                use_cache=params["use_cache"],
                force_live=params["force_live"],
                idusuario=idusuario,
                errors_only=params["errors_only"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return _user_kardex_report_response(report)


class ComplianceKardexErrorsView(APIView):
    """
    Full error detail for one kardex (SISGEN + UIF + PDT placeholder).

    GET /compliance/kardex/<kardex>/errors/
      - cache=true (optional) — read KardexComplianceCache instead of live validation
      - source=uif|sisgen (optional) — filter one source

  Live by default: fixes in the DB show on the next request without refresh.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, kardex: str):
        use_cache = request.query_params.get("cache", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        source = (request.query_params.get("source") or "").strip().lower() or None
        if source and source not in SUPPORTED_SOURCES:
            return Response(
                {
                    "error": "Invalid source. Use: uif, sisgen",
                    "supported_sources": sorted(SUPPORTED_SOURCES),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = KardexComplianceDetailService()
        try:
            detail = service.build_detail(
                kardex,
                use_cache=use_cache,
                source_filter=source,
            )
        except KardexNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ComplianceCacheNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        return Response(detail, status=status.HTTP_200_OK)


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
    """
    GET single kardex compliance detail.

    Same as ``/compliance/kardex/<kardex>/errors/`` (live validation by default).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, kardex: str):
        return ComplianceKardexErrorsView().get(request, kardex=kardex)
