"""
SISGEN-native validation strings (errores / observaciones / personas).

Uses DocumentSearchService — same path as SisgenValidationRecalculateView.
Does not include nested uif_validation (that lives under sources.uif).
"""

import logging

from sisgen.services.document_search_service import DocumentSearchService

from compliance.services.payload import build_sisgen_block

logger = logging.getLogger(__name__)


def collect_sisgen_issues(kardex: str) -> dict:
    service = DocumentSearchService()
    docs = service._execute_batch_query([kardex])
    if not docs:
        return build_sisgen_block(errores=[], observaciones=[], personas=[])

    service.kardex_errors = {}
    service.kardex_observations = {}
    service.person_errors = {}
    service.pdt_errors = {}

    try:
        service._validate_document_data(docs)
        service._validate_person_data(docs)
        # PDT skipped — compliance PDT block stays pending
    except Exception as exc:
        logger.warning("SISGEN validation warning for %s: %s", kardex, exc)

    processed = service._process_documents(docs, filters={})
    if not processed:
        return build_sisgen_block(errores=[], observaciones=[], personas=[])

    doc = processed[0]
    return build_sisgen_block(
        errores=doc.get("errores") or [],
        observaciones=doc.get("observaciones") or [],
        personas=doc.get("personas") or [],
    )
