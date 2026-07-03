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
