"""
UIF error counts for compliance — same engine as the UIF report/dashboard.

Source of truth: ``UifDashboardService.run`` (load → threshold → validate).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, Optional

from notaria import models
from uif.services.dashboard_service import UifDashboardService


def count_uif_errors_by_kardex(
    start_date: date,
    end_date: date,
    *,
    idusuario: Optional[int] = None,
) -> Dict[str, int]:
    """
    Per-kardex UIF field-error counts for ``[start_date, end_date]``.

    Matches UIF report ``summary.total_errors`` when summed (before optional
    ``idusuario`` filter). Includes complementary tipo ``C`` and threshold gating.
    """
    initial = start_date.strftime("%d/%m/%Y")
    final = end_date.strftime("%d/%m/%Y")
    payload = UifDashboardService().run(
        start_date,
        end_date,
        initial,
        final,
        include_valid=False,
    )

    counts: Dict[str, int] = defaultdict(int)
    for row in payload.get("lista_kardex_report") or []:
        key = str(row.get("kardex") or "").strip()
        n = int(row.get("validation_error_count") or 0)
        if key and n > 0:
            counts[key] += n

    if not counts:
        return {}

    if idusuario is not None:
        allowed = {
            str(k).strip()
            for k in models.Kardex.objects.filter(
                kardex__in=list(counts.keys()),
                idusuario=idusuario,
            ).values_list("kardex", flat=True)
            if k and str(k).strip()
        }
        return {k: v for k, v in counts.items() if k in allowed}

    return dict(counts)
