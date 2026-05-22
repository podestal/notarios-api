"""
Report payload — reuses the UIF dashboard pipeline (single source of truth).
"""

from datetime import date
from typing import Any, Dict, Optional, Tuple

from uif.services.dashboard_service import UifDashboardService


def get_uif_report_data(
    start_date: date,
    end_date: date,
    initial_date: str,
    final_date: str,
    report_policy: str = "all",
) -> Dict[str, Any]:
    """Run full dashboard logic and return data for Excel / plane reports."""
    payload = UifDashboardService().run(
        start_date, end_date, initial_date, final_date, include_valid=False
    )
    payload["report_policy"] = normalize_report_policy(report_policy)
    payload["lista_kardex_report_active"] = select_report_records(payload, payload["report_policy"])
    return payload


def normalize_report_policy(value: Optional[str]) -> str:
    """`all` = PHP _arrObjRo parity; `clean` = only acts with zero field errors."""
    policy = (value or "all").strip().lower()
    if policy in ("all", "legacy", "php"):
        return "all"
    if policy in ("clean", "valid", "zero_errors"):
        return "clean"
    return "all"


def select_report_records(payload: Dict[str, Any], report_policy: str) -> list:
    if report_policy == "clean":
        return list(payload.get("lista_kardex_ro") or [])
    return list(
        payload.get("lista_kardex_report")
        or payload.get("lista_kardex_ro")
        or []
    )


def parse_report_dates(initial_date: str, final_date: str) -> Tuple[date, date]:
    from uif.services.date_utils import parse_date_range
    from rest_framework.response import Response

    parsed = parse_date_range(initial_date, final_date)
    if isinstance(parsed, Response):
        raise ValueError(
            parsed.data.get("error", "Invalid date format. Use DD/MM/YYYY or YYYY-MM-DD")
        )
    return parsed
