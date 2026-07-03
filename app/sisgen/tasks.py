from celery import shared_task


@shared_task(bind=True, name="sisgen.run_send_job")
def run_send_job(self, job_id: int) -> int:
    from sisgen.services.send_job_executor import execute_send_job

    execute_send_job(job_id, celery_task_id=self.request.id or "")
    return job_id
