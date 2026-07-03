from celery import shared_task


@shared_task(
    bind=True,
    name="sisgen.send_job",
    autoretry_for=(),
    max_retries=0,
)
def send_job(self, job_id: int) -> int:
    """Orchestrator: load job, send in batches of 10, persist progress + result."""
    from sisgen.services.send_job_executor import execute_send_job

    execute_send_job(job_id, celery_task_id=self.request.id or "")
    return job_id


# Backward-compatible alias (Step 2 name).
run_send_job = send_job
