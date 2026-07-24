"""
Even split of money or percentages for kardex calculate (PHP divide() parity, cent-safe).
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Optional, Union

Number = Union[int, float, str, Decimal]


def _to_cents(total: Number) -> int:
    quantized = Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(quantized * 100)


def divide_evenly(count: int, total: Number) -> List[float]:
    """
    Split ``total`` into ``count`` parts that sum exactly (2 decimal places).

  Uses integer cents so 24900 / 3 → [8300.0, 8300.0, 8300.0], not 8299.17 from
  multiplying 33.33% × importe.
    """
    if count <= 0:
        return []
    if count == 1:
        return [float(Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))]

    total_cents = _to_cents(total)
    base_cents = total_cents // count
    extra = total_cents % count

    parts: List[float] = []
    for i in range(count):
        cents = base_cents + (1 if i < extra else 0)
        parts.append(cents / 100.0)
    return parts


def parse_finite_decimal(value: Number, *, field: str = "value") -> Optional[Decimal]:
    """
    Parse a finite Decimal or return None for blank.

    Rejects inf / -inf / nan / non-numeric strings (e.g. \"Infinity\" from JS
    ``(x/0).toString()``).
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number (got non-finite float).")
    try:
        dec = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a valid number.") from exc
    if not dec.is_finite():
        raise ValueError(f"{field} must be a finite number (got {value!r}).")
    return dec


def format_monto(amount: Number) -> str:
    dec = parse_finite_decimal(amount, field="monto")
    if dec is None:
        return "0.00"
    return str(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_porcentaje(amount: Number) -> str:
    dec = parse_finite_decimal(amount, field="porcentaje")
    if dec is None:
        return "0.00"
    return str(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
