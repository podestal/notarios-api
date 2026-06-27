"""
SISGEN-native validation strings (errores / observaciones / personas).

Uses DocumentSearchService — same path as SisgenValidationRecalculateView.
Does not include nested uif_validation (that lives under sources.uif).
"""

import logging

from sisgen.services.document_search_service import DocumentSearchService

from compliance.services.payload import build_sisgen_block

logger = logging.getLogger(__name__)


def bulk_collect_sisgen_issue_counts(kardex_list: list) -> dict:
    """
    Batch SISGEN pre-send validation counts via DocumentSearchService (one pass).

    Returns ``{kardex: {error_count, has_errors}}``.
    ``error_count`` = len(errores) only (kardex-level errors; not personas/observaciones).
    """
    keys = [str(k or "").strip() for k in kardex_list if k and str(k).strip()]
    empty = {"error_count": 0, "has_errors": False}
    if not keys:
        return {}

    service = DocumentSearchService()
    docs = service._execute_batch_query(keys)
    if not docs:
        return {k: dict(empty) for k in keys}

    service.kardex_errors = {}
    service.kardex_observations = {}
    service.person_errors = {}
    service.pdt_errors = {}

    try:
        # Document-level errores only; skip person validation (personas) for this report.
        prefetch = service._prefetch_document_validation_data(keys)
        service._validate_document_data(docs, validation_prefetch=prefetch)
    except Exception as exc:
        logger.warning("SISGEN batch validation warning: %s", exc)

    out: dict = {k: dict(empty) for k in keys}
    for k in keys:
        error_count = len(service.kardex_errors.get(k, []))
        out[k] = {
            "error_count": error_count,
            "has_errors": error_count > 0,
        }
    return out


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
