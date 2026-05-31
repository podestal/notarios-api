"""
Pre-send SISGEN validation errors for a single kardex (errores / observaciones / personas).
"""

import logging
from typing import Any, Dict, Optional

from sisgen.services.document_search_service import DocumentSearchService
from sisgen.services.search_response import count_sisgen_errors

logger = logging.getLogger(__name__)


def collect_kardex_sisgen_errors(kardex: str) -> Optional[Dict[str, Any]]:
    """
    Run DocumentSearchService validations for one kardex.

    Returns None when the kardex does not exist. UIF and PDT blocks are not included.
    """
    kardex = (kardex or "").strip()
    if not kardex:
        return None

    service = DocumentSearchService()
    docs = service._execute_batch_query([kardex])
    if not docs:
        return None

    service.kardex_errors = {}
    service.kardex_observations = {}
    service.person_errors = {}
    service.pdt_errors = {}

    try:
        service._validate_document_data(docs)
        service._validate_person_data(docs)
    except Exception as exc:
        logger.warning("SISGEN validation warning for %s: %s", kardex, exc)

    processed = service._process_documents(docs, filters={})
    if not processed:
        return None

    doc = processed[0]
    row = {
        "errores": list(doc.get("errores") or []),
        "observaciones": list(doc.get("observaciones") or []),
        "personas": list(doc.get("personas") or []),
    }
    return {
        "error": 0,
        "kardex": doc.get("kardex", kardex),
        "idkardex": str(doc.get("idkardex", "")),
        "sisgen_error_count": count_sisgen_errors(row),
        "errores": row["errores"],
        "observaciones": row["observaciones"],
        "personas": row["personas"],
    }
