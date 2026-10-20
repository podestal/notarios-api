"""PDT issues for compliance — same four checks as getErrors.php / Mis errores PDT."""

from __future__ import annotations

from typing import Dict, List

from compliance.services.payload import build_pdt_block
from notaria.services.pdt_mis_errores_service import (
    count_errors_by_kardex,
    list_errors_for_kardex,
)


def collect_pdt_issues(kardex: str) -> dict:
    return build_pdt_block(list_errors_for_kardex(kardex))


def bulk_collect_pdt_error_counts(kardex_keys: List[str]) -> Dict[str, int]:
    return count_errors_by_kardex(kardex_keys)
