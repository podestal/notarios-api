"""
Celery orchestrator: run a SisgenSendJob in batches of 10 (inline, no sub-tasks yet).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sisgen.models import SisgenSendJob
from sisgen.services.send_job_store import (
    complete_job,
    fail_job,
    mark_job_documents_running,
    set_job_running,
    sync_job_documents_after_batch,
    update_job_progress,
)
from sisgen.services.sisgen_send_service import (
    DEFAULT_BATCH_SIZE,
    finalize_combined_result,
    merge_batch_result,
    new_combined_result,
    send_batch,
)

logger = logging.getLogger(__name__)


def run_send_job_orchestrator(
    job: SisgenSendJob,
    *,
    documents: List[Dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
    **send_kwargs: Any,
) -> Dict[str, Any]:
    """
    Chunk documents, send each batch inline, update job progress + child rows.
    """
    combined = new_combined_result(dry_run=send_kwargs.get("dry_run", False))
    total = len(documents)
    expected_batches = (total + batch_size - 1) // batch_size if total else 0
    processed = 0

    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        batch_num = (i // batch_size) + 1

        mark_job_documents_running(job, batch=batch, batch_index=batch_num)

        batch_result = send_batch(
            batch=batch,
            batch_index=batch_num,
            user=job.user,
            **send_kwargs,
        )
        merge_batch_result(combined, batch_result)
        sync_job_documents_after_batch(job, batch=batch, batch_result=batch_result)

        processed += len(batch)
        update_job_progress(job, processed=processed, total=total)

    return finalize_combined_result(
        combined,
        documents,
        total=total,
        expected_batches=expected_batches,
    )


def execute_send_job(job_id: int, *, celery_task_id: str = "") -> SisgenSendJob:
    job = SisgenSendJob.objects.select_related("user").prefetch_related("documents").get(
        pk=job_id
    )
    if job.status not in (
        SisgenSendJob.Status.PENDING,
        SisgenSendJob.Status.RUNNING,
    ):
        return job

    set_job_running(job, celery_task_id)
    documents = (job.payload or {}).get("documents") or []

    try:
        result = run_send_job_orchestrator(job, documents=documents)
        complete_job(job, result)
        return job
    except Exception as exc:
        logger.exception("SisgenSendJob %s failed: %s", job_id, exc)
        fail_job(job, str(exc))
        raise
