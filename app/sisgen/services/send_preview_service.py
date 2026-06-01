"""
Resolve all kardexes matching SISGEN search filters (send preview / filter validation).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sisgen.services.document_search_service import DocumentSearchService
from sisgen.utils.exceptions import DocumentSearchException, ValidationException
from sisgen.utils.validators import SearchFiltersValidator

logger = logging.getLogger(__name__)

SEARCH_FILTER_KEYS = (
    "fechaDesde",
    "fechaHasta",
    "tipoInstrumento",
    "estado",
    "codigoActo",
)


def extract_search_filters(data: Dict[str, Any]) -> Dict[str, Any]:
    """Same fields as POST /sisgen/search/ (ignores page, search_id, documents)."""
    if not isinstance(data, dict):
        return {}
    return {key: data[key] for key in SEARCH_FILTER_KEYS if key in data}


def validate_search_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    return SearchFiltersValidator().validate(filters)


def build_send_preview(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    All documents matching filters (not paginated): kardex, idkardex, contrato.
    """
    if int(filters.get("tipoInstrumento") or 0) == 5:
        raise DocumentSearchException(
            "La vista previa de envío por filtros no aplica a libros (tipoInstrumento 5). "
            "Use el flujo de búsqueda de libros."
        )

    service = DocumentSearchService()
    validated = validate_search_filters(filters)
    documents = service._execute_search_query(validated)

    preview_documents: List[Dict[str, Any]] = []
    for doc in documents:
        preview_documents.append(
            {
                "kardex": doc.get("kardex") or "",
                "idkardex": str(doc.get("idkardex", "")),
                "contrato": (doc.get("contrato") or "").strip(),
            }
        )

    return {
        "error": 0,
        "total": len(preview_documents),
        "filters": validated,
        "documents": preview_documents,
    }


def resolve_documents_from_filters(filters: Dict[str, Any]) -> Dict[str, str]:
    """Map kardex -> idkardex for all rows matching filters."""
    if int(filters.get("tipoInstrumento") or 0) == 5:
        return {}
    service = DocumentSearchService()
    validated = validate_search_filters(filters)
    documents = service._execute_search_query(validated)
    out: Dict[str, str] = {}
    for doc in documents:
        k = str(doc.get("kardex") or "").strip()
        if k:
            out[k] = str(doc.get("idkardex", ""))
    return out


def verify_documents_against_filters(
    filters: Dict[str, Any], documents: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Return (normalized documents, list of kardex not matching filters).
    """
    allowed = resolve_documents_from_filters(filters)
    normalized: List[Dict[str, str]] = []
    invalid: List[str] = []

    for item in documents or []:
        kardex = str(item.get("kardex") or "").strip()
        idkardex = str(item.get("idkardex") or "").strip()
        if not kardex or not idkardex:
            continue
        if kardex not in allowed:
            invalid.append(kardex)
            continue
        if allowed[kardex] != idkardex:
            invalid.append(kardex)
            continue
        normalized.append({"kardex": kardex, "idkardex": idkardex})

    return normalized, invalid
