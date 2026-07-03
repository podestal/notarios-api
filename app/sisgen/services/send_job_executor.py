"""
Celery orchestrator: batches of 10 with fan-out to single-doc sends on batch failure.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sisgen.models import SisgenSendJob, SisgenSendJobDocument
from sisgen.services.send_batch_summary import (
    BATCH_STATUS_FAN_OUT,
    build_batch_summary_entry,
    should_fan_out_batch,
)
from sisgen.services.send_job_store import (
    complete_job,
    fail_job,
    mark_job_documents_running,
    set_job_running,
    sync_job_documents_after_batch,
    sync_job_documents_after_send,
    update_job_progress,
)
from sisgen.services.sisgen_send_service import (
    DEFAULT_BATCH_SIZE,
    finalize_combined_result,
    merge_batch_result,
    new_combined_result,
    send_batch,
    send_single,
)

logger = logging.getLogger(__name__)


def fan_out_batch_to_singles(
    job: SisgenSendJob,
    *,
    batch: List[Dict[str, Any]],
    batch_index: int,
    batch_result: Dict[str, Any],
    combined: Dict[str, Any],
    **send_kwargs: Any,
) -> None:
    """
    After a batch-level failure, send each document once as a batch of 1.
    """
    merge_batch_result(combined, batch_result)

    summary = batch_result.get("batch_summary") or {}
    logger.warning(
        "SISGEN batch %s failed (%s); fan-out to %s single sends for job %s",
        batch_index,
        summary.get("status"),
        len(batch),
        job.pk,
    )

    combined["batches"].append(
        build_batch_summary_entry(
            batch_index=batch_index,
            batch=batch,
            status=BATCH_STATUS_FAN_OUT,
            attempted=True,
            message=(
                f"Batch failed ({summary.get('status')}); "
                f"retrying {len(batch)} document(s) individually."
            ),
        )
    )

    for doc in batch:
        mark_job_documents_running(
            job,
            batch=[doc],
            batch_index=batch_index,
            attempt=SisgenSendJobDocument.Attempt.SINGLE,
        )
        single_result = send_single(
            doc,
            batch_index=batch_index,
            user=job.user,
            **send_kwargs,
        )
        merge_batch_result(combined, single_result)
        sync_job_documents_after_send(
            job,
            batch=[doc],
            batch_result=single_result,
            attempt=SisgenSendJobDocument.Attempt.SINGLE,
        )


def process_batch_with_fanout(
    job: SisgenSendJob,
    *,
    batch: List[Dict[str, Any]],
    batch_index: int,
    combined: Dict[str, Any],
    **send_kwargs: Any,
) -> None:
    mark_job_documents_running(
        job,
        batch=batch,
        batch_index=batch_index,
        attempt=SisgenSendJobDocument.Attempt.BATCH,
    )

    batch_result = send_batch(
        batch=batch,
        batch_index=batch_index,
        user=job.user,
        **send_kwargs,
    )

    if should_fan_out_batch(batch_result):
        fan_out_batch_to_singles(
            job,
            batch=batch,
            batch_index=batch_index,
            batch_result=batch_result,
            combined=combined,
            **send_kwargs,
        )
        return

    merge_batch_result(combined, batch_result)
    sync_job_documents_after_batch(job, batch=batch, batch_result=batch_result)


def run_send_job_orchestrator(
    job: SisgenSendJob,
    *,
    documents: List[Dict[str, Any]],
    batch_size: int = DEFAULT_BATCH_SIZE,
    **send_kwargs: Any,
) -> Dict[str, Any]:
    combined = new_combined_result(dry_run=send_kwargs.get("dry_run", False))
    total = len(documents)
    expected_batches = (total + batch_size - 1) // batch_size if total else 0
    processed = 0

    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        batch_num = (i // batch_size) + 1

        process_batch_with_fanout(
            job,
            batch=batch,
            batch_index=batch_num,
            combined=combined,
            **send_kwargs,
        )

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
