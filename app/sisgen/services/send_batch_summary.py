"""
Per-batch status rows for POST /sisgen/send-sisgen/ responses.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


BATCH_STATUS_COMPLETED = "completed"
BATCH_STATUS_SOAP_REJECTED = "soap_rejected"
BATCH_STATUS_SKIPPED_NO_XML = "skipped_no_xml"
BATCH_STATUS_DRY_RUN = "dry_run"
BATCH_STATUS_ERROR_PROCESSING = "error_processing"
BATCH_STATUS_ERROR_SEND = "error_send"
BATCH_STATUS_FAN_OUT = "fan_out"

# Batch-level outcomes where per-kardex outcome is unknown — retry each doc alone.
FAN_OUT_BATCH_STATUSES = frozenset(
    {
        BATCH_STATUS_SOAP_REJECTED,
        BATCH_STATUS_ERROR_SEND,
        BATCH_STATUS_ERROR_PROCESSING,
        BATCH_STATUS_SKIPPED_NO_XML,
    }
)


def should_fan_out_batch(batch_result: Dict[str, Any]) -> bool:
    """
    Fan-out when the whole batch failed at SOAP/XML level and multiple docs were bundled.
    Do not fan-out when SOAP returned per-document rows (COMPLETED with some FALLIDO).
    """
    summary = batch_result.get("batch_summary") or {}
    status = summary.get("status") or ""
    if status not in FAN_OUT_BATCH_STATUSES:
        return False
    kardexes = summary.get("kardex") or []
    return len(kardexes) > 1


def snapshot_batch_documents(batch: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for doc in batch:
        k = str(doc.get("kardex") or "").strip()
        if not k:
            continue
        out.append(
            {
                "kardex": k,
                "idkardex": str(doc.get("idkardex") or ""),
            }
        )
    return out


def build_batch_summary_entry(
    *,
    batch_index: int,
    batch: List[Dict[str, Any]],
    status: str,
    attempted: bool,
    message: str = "",
    http_status: Optional[int] = None,
    soap_return_status: str = "",
    xml_issues: Optional[List[str]] = None,
    guardados: int = 0,
    fallidos: int = 0,
    observados: int = 0,
    submission_response_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    docs = snapshot_batch_documents(batch)
    return {
        "batch_index": batch_index,
        "status": status,
        "attempted": attempted,
        "kardex": [d["kardex"] for d in docs],
        "documents": docs,
        "http_status": http_status,
        "soap_return_status": soap_return_status or None,
        "message": message,
        "xml_issues": list(xml_issues or []),
        "guardados": guardados,
        "fallidos": fallidos,
        "observados": observados,
        "submission_response_ids": list(submission_response_ids or []),
    }


def aggregate_batch_summary(
    batches: List[Dict[str, Any]],
    *,
    total_documents: int,
    expected_batches: int,
) -> Dict[str, Any]:
    by_status: Dict[str, int] = {}
    for row in batches:
        st = row.get("status") or "unknown"
        by_status[st] = by_status.get(st, 0) + 1

    attempted_docs = sum(
        len(row.get("kardex") or [])
        for row in batches
        if row.get("attempted")
    )

    return {
        "expected_batches": expected_batches,
        "reported_batches": len(batches),
        "total_documents": total_documents,
        "documents_soap_attempted": attempted_docs,
        "completed": by_status.get(BATCH_STATUS_COMPLETED, 0),
        "soap_rejected": by_status.get(BATCH_STATUS_SOAP_REJECTED, 0),
        "skipped_no_xml": by_status.get(BATCH_STATUS_SKIPPED_NO_XML, 0),
        "dry_run": by_status.get(BATCH_STATUS_DRY_RUN, 0),
        "error_processing": by_status.get(BATCH_STATUS_ERROR_PROCESSING, 0),
        "error_send": by_status.get(BATCH_STATUS_ERROR_SEND, 0),
        "fan_out": by_status.get(BATCH_STATUS_FAN_OUT, 0),
        "all_batches_completed": (
            len(batches) == expected_batches
            and by_status.get(BATCH_STATUS_SOAP_REJECTED, 0) == 0
            and by_status.get(BATCH_STATUS_ERROR_SEND, 0) == 0
            and by_status.get(BATCH_STATUS_ERROR_PROCESSING, 0) == 0
            and by_status.get(BATCH_STATUS_SKIPPED_NO_XML, 0) == 0
        ),
    }
