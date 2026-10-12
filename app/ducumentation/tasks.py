from celery import shared_task


@shared_task(
    bind=True,
    name="ducumentation.backup_document_to_r2",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=8,
    acks_late=True,
    ignore_result=True,
)
def backup_document_to_r2(self, object_key: str) -> bool:
    """Mirror a locally saved document to Cloudflare R2 (reads the file from the shared volume)."""
    from .storage_backends import backup_local_object_to_r2

    return backup_local_object_to_r2(object_key)
