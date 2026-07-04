"""
Backoff schedules for SUNAT outbox retries (America/Lima).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from taxes.models import SunatOutbox

# Factura lane: 5m → 15m → 30m → 1h → then 2h
RECIBO_RETRY_DELAYS_SECONDS = (300, 900, 1800, 3600, 7200)

# Resumen lane: 30m → 2h (steady)
RESUMEN_RETRY_DELAYS_SECONDS = (1800, 7200)

# Ticket still processing at SUNAT
RESUMEN_POLL_DELAY_SECONDS = 180


def _delay_for_attempt(*, kind: str, phase: str, attempt_count: int) -> int:
    if kind == SunatOutbox.Kind.RESUMEN and phase == SunatOutbox.Phase.POLL:
        return RESUMEN_POLL_DELAY_SECONDS

    if kind == SunatOutbox.Kind.RESUMEN:
        delays = RESUMEN_RETRY_DELAYS_SECONDS
    else:
        delays = RECIBO_RETRY_DELAYS_SECONDS

    index = max(0, min(attempt_count - 1, len(delays) - 1))
    return delays[index]


def compute_next_retry_at(
    *,
    kind: str,
    phase: str,
    attempt_count: int,
    from_time: datetime | None = None,
) -> datetime:
    base = from_time or timezone.now()
    delay = _delay_for_attempt(kind=kind, phase=phase, attempt_count=attempt_count)
    return base + timedelta(seconds=delay)
