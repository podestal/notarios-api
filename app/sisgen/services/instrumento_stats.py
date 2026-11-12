"""
Correlative Nº instrumento stats for a SISGEN send/request document set.

Rule: N kardex ⇒ N instrument numbers, consecutive from first→last with no gaps.
Example OK: 5 kardex, instruments 10..14.
Example FAIL: 5 kardex, instruments 1,2,3,5,6 (gap at 4; span 6 ≠ 5).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


def parse_instrumento_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    digits = "".join(c for c in str(value).strip() if c.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def build_instrumento_stats(
    documents: Sequence[Dict[str, Any]],
    *,
    instrumento_keys: Iterable[str] = (
        "numero_instrumento",
        "numescritura",
        "numinstrmento",
    ),
) -> Dict[str, Any]:
    """
    Return stats for the request:

    - kardex_count
    - instrumento_first / instrumento_last
    - instrumento_expected (last - first + 1 when both present)
    - instrumento_unique (distinct parsed numbers)
    - correlative_ok (no gaps, no duplicates, counts match)
    - gaps / duplicates / missing_instrumento
    """
    keys = tuple(instrumento_keys)
    kardex_count = len(documents)
    numbers: List[int] = []
    missing = 0

    for doc in documents:
        raw = None
        for key in keys:
            if doc.get(key) not in (None, ""):
                raw = doc.get(key)
                break
        parsed = parse_instrumento_int(raw)
        if parsed is None:
            missing += 1
        else:
            numbers.append(parsed)

    unique_sorted = sorted(set(numbers))
    duplicates: List[int] = sorted(
        {n for n in numbers if numbers.count(n) > 1}
    )
    first = unique_sorted[0] if unique_sorted else None
    last = unique_sorted[-1] if unique_sorted else None
    expected = (last - first + 1) if first is not None and last is not None else None

    gaps: List[int] = []
    if first is not None and last is not None:
        present: Set[int] = set(unique_sorted)
        gaps = [n for n in range(first, last + 1) if n not in present]

    correlative_ok = (
        kardex_count > 0
        and missing == 0
        and not duplicates
        and not gaps
        and expected is not None
        and expected == kardex_count
        and len(unique_sorted) == kardex_count
    )

    return {
        "kardex_count": kardex_count,
        "instrumento_first": first,
        "instrumento_last": last,
        "instrumento_expected": expected,
        "instrumento_unique": len(unique_sorted),
        "missing_instrumento": missing,
        "gaps": gaps,
        "duplicates": duplicates,
        "correlative_ok": correlative_ok,
    }
