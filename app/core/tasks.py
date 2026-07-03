from celery import shared_task


@shared_task(name="core.ping")
def ping(message: str = "pong") -> dict:
    """
    Smoke-test task. Runs only when enqueued (delay / apply_async), not on a schedule.
    """
    return {"status": "ok", "message": message}
