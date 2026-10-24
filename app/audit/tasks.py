import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="audit.persist_kardex_change", ignore_result=True)
def persist_kardex_change(payload: dict) -> int:
    from audit.services import persist_kardex_change_sync

    try:
        return persist_kardex_change_sync(payload)
    except Exception:
        logger.exception("Celery kardex audit persist failed")
        return 0
