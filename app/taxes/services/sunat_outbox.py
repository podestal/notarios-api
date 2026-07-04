"""
Persist and schedule SUNAT retry jobs (outbox pattern).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.db import transaction
from django.utils import timezone

from taxes.models import SunatOutbox
from taxes.services.sunat_retry_schedule import compute_next_retry_at

logger = logging.getLogger(__name__)


def _schedule_outbox_task(outbox_id: int, *, countdown: int) -> None:
    from taxes.tasks import process_sunat_outbox_item

    async_result = process_sunat_outbox_item.apply_async(
        args=[outbox_id],
        countdown=max(0, countdown),
    )
    SunatOutbox.objects.filter(pk=outbox_id).update(
        celery_task_id=async_result.id or "",
        updated_at=timezone.now(),
    )


def _countdown_until(when) -> int:
    delta = (when - timezone.now()).total_seconds()
    return max(0, int(delta))


def enqueue_recibo_send(
    *,
    recibo_id: int,
    last_error: str = "",
    attempt_count: int = 1,
) -> SunatOutbox:
    return _enqueue(
        kind=SunatOutbox.Kind.RECIBO,
        target_id=recibo_id,
        phase=SunatOutbox.Phase.SEND,
        last_error=last_error,
        attempt_count=attempt_count,
    )


def enqueue_resumen_send(
    *,
    resumen_id: int,
    last_error: str = "",
    attempt_count: int = 1,
    phase: str = SunatOutbox.Phase.SEND,
    metadata: Optional[Dict[str, Any]] = None,
) -> SunatOutbox:
    return _enqueue(
        kind=SunatOutbox.Kind.RESUMEN,
        target_id=resumen_id,
        phase=phase,
        last_error=last_error,
        attempt_count=attempt_count,
        metadata=metadata,
    )


@transaction.atomic
def _enqueue(
    *,
    kind: str,
    target_id: int,
    phase: str,
    last_error: str,
    attempt_count: int,
    metadata: Optional[Dict[str, Any]] = None,
) -> SunatOutbox:
    next_retry_at = compute_next_retry_at(
        kind=kind,
        phase=phase,
        attempt_count=attempt_count,
    )
    outbox, created = SunatOutbox.objects.select_for_update().get_or_create(
        kind=kind,
        target_id=target_id,
        defaults={
            "status": SunatOutbox.Status.PENDING,
            "phase": phase,
            "attempt_count": attempt_count,
            "next_retry_at": next_retry_at,
            "last_error": last_error[:4000],
            "metadata": metadata or {},
        },
    )
    if not created:
        merged_meta = {**(outbox.metadata or {}), **(metadata or {})}
        outbox.status = SunatOutbox.Status.PENDING
        outbox.phase = phase
        outbox.attempt_count = attempt_count
        outbox.next_retry_at = next_retry_at
        outbox.last_error = last_error[:4000]
        outbox.metadata = merged_meta
        outbox.completed_at = None
        outbox.celery_task_id = ""
        outbox.save(
            update_fields=[
                "status",
                "phase",
                "attempt_count",
                "next_retry_at",
                "last_error",
                "metadata",
                "completed_at",
                "celery_task_id",
                "updated_at",
            ]
        )

    transaction.on_commit(
        lambda: _schedule_outbox_task(
            outbox.pk,
            countdown=_countdown_until(outbox.next_retry_at),
        )
    )
    return outbox


def get_active_outbox(*, kind: str, target_id: int) -> Optional[SunatOutbox]:
    return (
        SunatOutbox.objects.filter(
            kind=kind,
            target_id=target_id,
            status__in=(
                SunatOutbox.Status.PENDING,
                SunatOutbox.Status.PROCESSING,
            ),
        )
        .order_by("-updated_at")
        .first()
    )


def mark_outbox_processing(outbox: SunatOutbox, *, celery_task_id: str = "") -> SunatOutbox:
    outbox.status = SunatOutbox.Status.PROCESSING
    outbox.celery_task_id = celery_task_id or outbox.celery_task_id
    outbox.save(update_fields=["status", "celery_task_id", "updated_at"])
    return outbox


def mark_outbox_completed(outbox: SunatOutbox) -> SunatOutbox:
    outbox.status = SunatOutbox.Status.COMPLETED
    outbox.completed_at = timezone.now()
    outbox.last_error = ""
    outbox.save(update_fields=["status", "completed_at", "last_error", "updated_at"])
    return outbox


def mark_outbox_failed(outbox: SunatOutbox, *, error: str) -> SunatOutbox:
    outbox.status = SunatOutbox.Status.FAILED
    outbox.last_error = (error or "")[:4000]
    outbox.completed_at = timezone.now()
    outbox.save(
        update_fields=["status", "last_error", "completed_at", "updated_at"]
    )
    return outbox


def schedule_outbox_retry(
    outbox: SunatOutbox,
    *,
    last_error: str,
    phase: str | None = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SunatOutbox:
    attempt = outbox.attempt_count + 1
    if attempt > outbox.max_attempts:
        return mark_outbox_failed(
            outbox,
            error=last_error or "Se agotaron los reintentos automáticos a SUNAT.",
        )

    phase_value = phase or outbox.phase
    next_retry_at = compute_next_retry_at(
        kind=outbox.kind,
        phase=phase_value,
        attempt_count=attempt,
    )
    merged_meta = {**(outbox.metadata or {}), **(metadata or {})}
    outbox.status = SunatOutbox.Status.PENDING
    outbox.phase = phase_value
    outbox.attempt_count = attempt
    outbox.next_retry_at = next_retry_at
    outbox.last_error = (last_error or "")[:4000]
    outbox.metadata = merged_meta
    outbox.save(
        update_fields=[
            "status",
            "phase",
            "attempt_count",
            "next_retry_at",
            "last_error",
            "metadata",
            "updated_at",
        ]
    )
    transaction.on_commit(
        lambda oid=outbox.pk, when=next_retry_at: _schedule_outbox_task(
            oid,
            countdown=_countdown_until(when),
        )
    )
    return outbox


def due_outbox_ids(*, limit: int = 50) -> list[int]:
    now = timezone.now()
    return list(
        SunatOutbox.objects.filter(
            status=SunatOutbox.Status.PENDING,
            next_retry_at__lte=now,
        )
        .order_by("next_retry_at")
        .values_list("pk", flat=True)[:limit]
    )
