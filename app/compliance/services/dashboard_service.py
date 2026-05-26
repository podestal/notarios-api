"""
Paginated compliance dashboard — reads KardexComplianceCache (Option B).
"""

from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import QuerySet

from compliance.models import KardexComplianceCache
from compliance.services.payload import (
    SOURCE_SISGEN,
    SOURCE_UIF,
    SUPPORTED_SOURCES,
    serialize_cache_row,
)


def parse_idtipkar_list(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    values = []
    for part in str(raw).replace(" ", "").split(","):
        if not part:
            continue
        try:
            values.append(int(part))
        except ValueError:
            continue
    return values


class ComplianceDashboardService:
    def build_list_queryset(
        self,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        idtipkar_list: Optional[List[int]] = None,
        source: Optional[str] = None,
        has_errors: Optional[bool] = True,
    ) -> QuerySet:
        qs = KardexComplianceCache.objects.all()
        if start_date and end_date:
            qs = qs.filter(fechaescritura__range=[start_date, end_date])
        if idtipkar_list:
            qs = qs.filter(idtipkar__in=idtipkar_list)
        if has_errors is True:
            if source == SOURCE_UIF:
                qs = qs.filter(uif_error_count__gt=0)
            elif source == SOURCE_SISGEN:
                qs = qs.filter(sisgen_error_count__gt=0)
            elif source in SUPPORTED_SOURCES:
                qs = qs.filter(has_errors=True)
            else:
                qs = qs.filter(has_errors=True)
        elif has_errors is False:
            qs = qs.filter(has_errors=False)
        return qs.order_by("-fechaescritura", "-updated_at")

    def aggregate_summary(
        self,
        qs: QuerySet,
        *,
        filters_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        total_cached = qs.count()
        with_errors = qs.filter(has_errors=True).count()
        uif_kardex = qs.filter(uif_error_count__gt=0).count()
        sisgen_kardex = qs.filter(sisgen_error_count__gt=0).count()
        return {
            "total_cached": total_cached,
            "with_errors": with_errors,
            "without_errors": total_cached - with_errors,
            "kardex_with_uif_errors": uif_kardex,
            "kardex_with_sisgen_errors": sisgen_kardex,
            "pdt": {"status": "pending", "note": "PDT not collected yet"},
            "filters": filters_meta,
        }

    def paginate_response(
        self,
        qs: QuerySet,
        *,
        paginate_fn,
        get_paginated_response_fn,
        source_filter: Optional[str],
        include_payload: bool,
        filters_meta: Dict[str, Any],
    ):
        summary = self.aggregate_summary(qs, filters_meta=filters_meta)
        page_qs = paginate_fn(qs)
        if page_qs is None:
            page_qs = []
        items = [
            serialize_cache_row(
                row,
                include_payload=include_payload,
                source_filter=source_filter,
            )
            for row in page_qs
        ]
        response = get_paginated_response_fn(items)
        if hasattr(response, "data") and isinstance(response.data, dict):
            response.data["summary"] = summary
        return response
