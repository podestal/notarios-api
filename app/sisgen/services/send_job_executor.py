"""
Run a persisted SisgenSendJob via the send service (used by Celery).
"""

from __future__ import annotations

import logging

from sisgen.models import SisgenSendJob
from sisgen.services.send_job_store import (
    complete_job,
    fail_job,
    set_job_running,
    update_job_progress,
)
from sisgen.services.sisgen_send_service import send_documents

logger = logging.getLogger(__name__)


def execute_send_job(job_id: int, *, celery_task_id: str = "") -> SisgenSendJob:
    job = SisgenSendJob.objects.select_related("user").get(pk=job_id)
    if job.status not in (
        SisgenSendJob.Status.PENDING,
        SisgenSendJob.Status.RUNNING,
    ):
        return job

    set_job_running(job, celery_task_id)
    documents = (job.payload or {}).get("documents") or []

    def on_batch_complete(processed: int, total: int) -> None:
        update_job_progress(job, processed=processed, total=total)

    try:
        result = send_documents(
            documents,
            user=job.user,
            on_batch_complete=on_batch_complete,
        )
        complete_job(job, result)
        return job
    except Exception as exc:
        logger.exception("SisgenSendJob %s failed: %s", job_id, exc)
        fail_job(job, str(exc))
        raise
