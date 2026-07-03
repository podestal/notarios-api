"""
Persistence for async SISGEN send jobs (Celery orchestrator reads/writes these rows).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from sisgen.models import (
    SisgenSendJob,
    SisgenSendJobDocument,
    SisgenSoapResponse,
)


def _normalize_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for doc in documents or []:
        kardex = str(doc.get("kardex") or "").strip()
        if not kardex or kardex in seen:
            continue
        seen.add(kardex)
        out.append(
            {
                "kardex": kardex,
                "idkardex": str(doc.get("idkardex") or ""),
            }
        )
    return out


@transaction.atomic
def create_send_job(
    *,
    user,
    documents: List[Dict[str, Any]],
    filters: Optional[Dict[str, Any]] = None,
) -> SisgenSendJob:
    """
    Create a pending job and one child row per kardex (deduped by kardex).
    """
    normalized = _normalize_documents(documents)
    job = SisgenSendJob.objects.create(
        user=user,
        status=SisgenSendJob.Status.PENDING,
        payload={
            "documents": normalized,
            "filters": dict(filters or {}),
        },
        progress_total=len(normalized),
        progress_processed=0,
    )
    SisgenSendJobDocument.objects.bulk_create(
        [
            SisgenSendJobDocument(
                job=job,
                kardex=doc["kardex"],
                idkardex=doc["idkardex"],
                status=SisgenSendJobDocument.Status.PENDING,
            )
            for doc in normalized
        ]
    )
    return job


def set_job_running(job: SisgenSendJob, celery_task_id: str) -> SisgenSendJob:
    job.status = SisgenSendJob.Status.RUNNING
    job.celery_task_id = celery_task_id or ""
    job.save(update_fields=["status", "celery_task_id", "updated_at"])
    return job


def update_job_progress(
    job: SisgenSendJob,
    *,
    processed: int,
    total: Optional[int] = None,
) -> SisgenSendJob:
    job.progress_processed = max(0, processed)
    if total is not None:
        job.progress_total = max(0, total)
    job.save(update_fields=["progress_processed", "progress_total", "updated_at"])
    return job


def complete_job(job: SisgenSendJob, result: Dict[str, Any]) -> SisgenSendJob:
    job.status = SisgenSendJob.Status.COMPLETED
    job.result = result or {}
    job.error = ""
    job.finished_at = timezone.now()
    job.save(
        update_fields=["status", "result", "error", "finished_at", "updated_at"]
    )
    return job


def fail_job(job: SisgenSendJob, error: str) -> SisgenSendJob:
    job.status = SisgenSendJob.Status.FAILED
    job.error = error or ""
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error", "finished_at", "updated_at"])
    return job


def mark_job_documents_running(
    job: SisgenSendJob,
    *,
    batch: List[Dict[str, Any]],
    batch_index: int,
    attempt: str = SisgenSendJobDocument.Attempt.BATCH,
) -> None:
    kardexes = [
        str(doc.get("kardex") or "").strip()
        for doc in batch
        if str(doc.get("kardex") or "").strip()
    ]
    if not kardexes:
        return
    SisgenSendJobDocument.objects.filter(job=job, kardex__in=kardexes).update(
        status=SisgenSendJobDocument.Status.RUNNING,
        batch_index=batch_index,
        attempt=attempt,
    )


def sync_job_documents_after_send(
    job: SisgenSendJob,
    *,
    batch: List[Dict[str, Any]],
    batch_result: Dict[str, Any],
    attempt: str,
) -> None:
    from sisgen.services.send_batch_summary import (
        BATCH_STATUS_COMPLETED,
        BATCH_STATUS_DRY_RUN,
        BATCH_STATUS_SKIPPED_NO_XML,
    )

    summary = batch_result.get("batch_summary") or {}
    batch_status = summary.get("status") or ""
    batch_index = int(summary.get("batch_index") or 0)
    message = summary.get("message") or ""
    submission_ids = summary.get("submission_response_ids") or []
    response_by_kardex: Dict[str, SisgenSoapResponse] = {}
    if submission_ids:
        for row in SisgenSoapResponse.objects.filter(pk__in=submission_ids):
            response_by_kardex[row.kardex] = row

    per_kardex_messages: Dict[str, str] = {}
    for row in (batch_result.get("merge") or {}).get("data") or []:
        k = str(row.get("kardex") or "").strip()
        if k:
            per_kardex_messages[k] = str(row.get("mensaje") or row.get("status") or "")

    if batch_status == BATCH_STATUS_COMPLETED:
        doc_status = SisgenSendJobDocument.Status.COMPLETED
    elif batch_status == BATCH_STATUS_SKIPPED_NO_XML:
        doc_status = SisgenSendJobDocument.Status.SKIPPED
    elif batch_status == BATCH_STATUS_DRY_RUN:
        doc_status = SisgenSendJobDocument.Status.COMPLETED
    else:
        doc_status = SisgenSendJobDocument.Status.FAILED

    for doc in batch:
        kardex = str(doc.get("kardex") or "").strip()
        if not kardex:
            continue
        try:
            job_doc = SisgenSendJobDocument.objects.get(job=job, kardex=kardex)
        except SisgenSendJobDocument.DoesNotExist:
            continue

        doc_message = per_kardex_messages.get(kardex) or message
        update_job_document(
            job_doc,
            status=doc_status,
            message=doc_message,
            batch_index=batch_index,
            attempt=attempt,
            submission_response=response_by_kardex.get(kardex),
        )


def sync_job_documents_after_batch(
    job: SisgenSendJob,
    *,
    batch: List[Dict[str, Any]],
    batch_result: Dict[str, Any],
) -> None:
    """Update per-kardex rows after a batch attempt (not single fan-out)."""
    sync_job_documents_after_send(
        job,
        batch=batch,
        batch_result=batch_result,
        attempt=SisgenSendJobDocument.Attempt.BATCH,
    )


def update_job_document(
    job_document: SisgenSendJobDocument,
    *,
    status: str,
    message: str = "",
    batch_index: Optional[int] = None,
    attempt: str = "",
    submission_response: Optional[SisgenSoapResponse] = None,
) -> SisgenSendJobDocument:
    job_document.status = status
    job_document.message = message or ""
    if batch_index is not None:
        job_document.batch_index = batch_index
    if attempt:
        job_document.attempt = attempt
    if submission_response is not None:
        job_document.submission_response = submission_response
    job_document.save()
    return job_document
