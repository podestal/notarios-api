from celery import shared_task


@shared_task(
    bind=True,
    name="taxes.sunat.process_outbox_item",
    autoretry_for=(),
    max_retries=0,
)
def process_sunat_outbox_item(self, outbox_id: int) -> int:
    from taxes.services.sunat_outbox_executor import execute_sunat_outbox

    execute_sunat_outbox(outbox_id, celery_task_id=self.request.id or "")
    return outbox_id


@shared_task(name="taxes.sunat.process_due_outbox")
def process_due_sunat_outbox() -> int:
    """Beat safety net: enqueue any due rows missed by ETA scheduling."""
    from taxes.services.sunat_outbox import due_outbox_ids
    from taxes.tasks import process_sunat_outbox_item

    count = 0
    for outbox_id in due_outbox_ids():
        process_sunat_outbox_item.delay(outbox_id)
        count += 1
    return count
