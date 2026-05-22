"""
UIF validation for SISGEN document search — delegates to the `uif` app engine.
"""

from typing import Dict, List

from uif.services.kardex_snapshot import (
    bulk_validate_kardex_numbers,
    validate_kardex_number,
)


class UIFValidationService:
    """Thin wrapper kept for stable imports from document_search_service."""

    def bulk_validate_kardex(self, kardex_numbers: List[str]) -> Dict[str, Dict]:
        return bulk_validate_kardex_numbers(kardex_numbers)

    def validate_kardex(self, kardex_number: str) -> Dict:
        return validate_kardex_number(kardex_number)
