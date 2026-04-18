"""Helpers for string-stored correlatives (legacy-style \"25\" not 25)."""

from __future__ import annotations

import re

from django.utils import timezone


def correlative_year_today() -> int:
    """Calendar year used to reset correlatives to 1 each January."""
    return timezone.localdate().year


def bump_int_string(value: str) -> str:
    """
    Parse a plain integer string, add one, return decimal string.
    Empty or non-numeric -> \"1\".
    """
    s = (value or "").strip()
    if not s:
        return "1"
    try:
        return str(int(s) + 1)
    except ValueError:
        return "1"


def bump_folio_papel_string(value: str) -> str:
    """
    Next folio/papel step from the previous value (Ayacucho VTA pattern).

    - \"000057 VTA\" -> \"000058\" (recto siguiente, sin VTA)
    - \"000058\" -> \"000058 VTA\" (reverso / mismo número con VTA)
    - \"000058 VTA\" -> \"000059\" (cierra verso, siguiente recto)
    - Legacy \"12v\" -> \"13\" (recto puro sin padding extra)
    """
    s = (value or "").strip()
    if not s:
        return "1"

    m_vta = re.match(r"^(\d+)\s+VTA\s*$", s, re.IGNORECASE)
    if m_vta:
        num_str = m_vta.group(1)
        n = int(num_str) + 1
        return str(n).zfill(len(num_str))

    if re.fullmatch(r"\d+", s):
        return f"{s} VTA"

    m_lv = re.fullmatch(r"(\d+)([vV])", s)
    if m_lv:
        num_str = m_lv.group(1)
        n = int(num_str) + 1
        return str(n).zfill(len(num_str))

    return "1"


def today_iso() -> str:
    return timezone.localdate().isoformat()
