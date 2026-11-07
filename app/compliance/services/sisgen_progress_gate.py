"""
Same SISGEN visibility rules as KardexComplianceDetailService.

When the kardex is already sent to SISGEN, or still lacks número de instrumento,
the errors panel does not report SISGEN gaps. Progress must follow that gate.
"""

from __future__ import annotations

from compliance.services.escrituracion_filter import has_escrituracion_info
from compliance.services.sisgen_sent_filter import is_kardex_sent_to_sisgen


def should_report_sisgen_issues(kardex_row) -> bool:
    if kardex_row is None:
        return False
    if is_kardex_sent_to_sisgen(getattr(kardex_row, "estado_sisgen", None)):
        return False
    if not has_escrituracion_info(kardex_row):
        return False
    return True
