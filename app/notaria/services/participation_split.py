"""
Even split of money or percentages for kardex calculate (PHP divide() parity, cent-safe).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Union

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


def format_monto(amount: Number) -> str:
    return str(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_porcentaje(amount: Number) -> str:
    return str(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
