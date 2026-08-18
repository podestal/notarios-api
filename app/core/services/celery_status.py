from __future__ import annotations

import os
import shelve
from datetime import datetime, timedelta
from typing import Any

from celery.schedules import crontab, schedule as IntervalSchedule
from django.conf import settings
from django.utils import timezone

from taxes.models import SunatOutbox

DEFAULT_BEAT_SCHEDULE_FILE = "/app/celerybeat-data/celerybeat-schedule"
FAILED_LIMIT = 50


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value).isoformat()


def _every_seconds(sched) -> float | None:
    if isinstance(sched, (int, float)):
        return float(sched)
    if isinstance(sched, IntervalSchedule):
        return sched.run_every.total_seconds()
    return None


def describe_schedule(sched) -> dict:
    every = _every_seconds(sched)
    if every is not None:
        if every >= 60 and every % 60 == 0:
            minutes = int(every // 60)
            human = f"every {minutes} minute(s)"
        else:
            human = f"every {int(every)} seconds"
        return {
            "type": "interval",
            "every_seconds": every,
            "schedule": human,
        }
    if isinstance(sched, crontab):
        return {
            "type": "crontab",
            "every_seconds": None,
            "schedule": str(sched),
        }
    return {
        "type": "unknown",
        "every_seconds": None,
        "schedule": str(sched),
    }


def next_run_at(sched, last_run_at: datetime | None, now: datetime | None = None) -> datetime | None:
    now = now or timezone.now()
    every = _every_seconds(sched)
    if every is not None:
        if last_run_at is None:
            return None
        nxt = last_run_at + timedelta(seconds=every)
        return now if nxt < now else nxt
    if hasattr(sched, "remaining_estimate") and last_run_at is not None:
        remaining = sched.remaining_estimate(last_run_at)
        return now + remaining
    return None


def _beat_schedule_filename() -> str:
    return (
        os.environ.get("CELERY_BEAT_SCHEDULE_FILENAME", "").strip()
        or DEFAULT_BEAT_SCHEDULE_FILE
    )


def read_beat_runtime(path: str | None = None) -> dict[str, dict]:
    filename = path or _beat_schedule_filename()
    if not os.path.exists(filename):
        return {}
    try:
        with shelve.open(filename, flag="r") as store:
            entries = store.get("entries") or {}
    except Exception:
        return {}

    runtime = {}
    for name, entry in entries.items():
        last_run = getattr(entry, "last_run_at", None)
        if last_run is not None and timezone.is_naive(last_run):
            last_run = timezone.make_aware(last_run, timezone.get_current_timezone())
        runtime[name] = {
            "last_run_at": last_run,
            "total_run_count": getattr(entry, "total_run_count", None),
        }
    return runtime


def list_beat_tasks(*, now: datetime | None = None) -> list[dict]:
    now = now or timezone.now()
    configured = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
    runtime = read_beat_runtime()
    rows = []
    for name, entry in configured.items():
        sched = entry.get("schedule")
        state = runtime.get(name) or {}
        last_run = state.get("last_run_at")
        rows.append(
            {
                "name": name,
                "task": entry.get("task"),
                **describe_schedule(sched),
                "last_run_at": _iso(last_run),
                "next_run_at": _iso(next_run_at(sched, last_run, now)),
                "run_count": state.get("total_run_count"),
            }
        )
    return rows


def _outbox_row(item: SunatOutbox) -> dict[str, Any]:
    return {
        "id": item.pk,
        "kind": item.kind,
        "target_id": item.target_id,
        "status": item.status,
        "phase": item.phase,
        "attempt_count": item.attempt_count,
        "max_attempts": item.max_attempts,
        "next_retry_at": _iso(item.next_retry_at),
        "last_error": item.last_error or "",
        "celery_task_id": item.celery_task_id or None,
        "updated_at": _iso(item.updated_at),
        "completed_at": _iso(item.completed_at),
    }


def list_sunat_outbox(*, status: str, limit: int = FAILED_LIMIT) -> list[dict]:
    qs = (
        SunatOutbox.objects.filter(status=status)
        .order_by("-updated_at")[:limit]
    )
    return [_outbox_row(item) for item in qs]


def celery_status_payload() -> dict:
    return {
        "beat_tasks": list_beat_tasks(),
        "sunat_retries": list_sunat_outbox(status=SunatOutbox.Status.PENDING)
        + list_sunat_outbox(status=SunatOutbox.Status.PROCESSING),
        "sunat_failed": list_sunat_outbox(status=SunatOutbox.Status.FAILED),
    }
