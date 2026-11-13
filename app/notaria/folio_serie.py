"""Folio / serie notarial: `123` or `123 VTA`. Final must be >= inicial."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_TOKEN_RE = re.compile(r"^(\d+)( VTA)?$", re.IGNORECASE)


def _parse(raw: Any) -> Optional[Tuple[int, bool]]:
    text = re.sub(r"\s+", " ", str(raw or "").strip())
    if not text:
        return None
    m = _TOKEN_RE.match(text)
    if not m:
        return None
    return int(m.group(1)), bool(m.group(2))


def _cmp(a: Any, b: Any) -> Optional[int]:
    pa, pb = _parse(a), _parse(b)
    if pa is None or pb is None:
        return None
    if pa[0] != pb[0]:
        return pa[0] - pb[0]
    return (1 if pa[1] else 0) - (1 if pb[1] else 0)


def folio_serie_page_count(ini: Any, fin: Any) -> int:
    pa, pb = _parse(ini), _parse(fin)
    if pa is None or pb is None:
        return 0
    start = pa[0] * 2 + (1 if pa[1] else 0)
    end = pb[0] * 2 + (1 if pb[1] else 0)
    return 0 if end < start else end - start + 1


def validate_folio_serie_pair(
    ini: Any,
    fin: Any,
    *,
    label_ini: str,
    label_fin: str,
    require_both: bool = False,
) -> List[str]:
    ini_t = re.sub(r"\s+", " ", str(ini or "").strip())
    fin_t = re.sub(r"\s+", " ", str(fin or "").strip())

    if not ini_t and not fin_t:
        return [f"Debe indicar {label_ini} y {label_fin}."] if require_both else []
    if bool(ini_t) != bool(fin_t):
        return [f"Debe completar ambos: {label_ini} y {label_fin}."]

    errs: List[str] = []
    tip = 'solo números o números + " VTA" (ej.: 10100 o 10100 VTA).'
    if _parse(ini_t) is None:
        errs.append(f"{label_ini}: {tip}")
    if _parse(fin_t) is None:
        errs.append(f"{label_fin}: {tip}")
    if errs:
        return errs

    if (_cmp(ini_t, fin_t) or 0) > 0:
        errs.append(f"{label_fin} ({fin_t}) no puede ser menor que {label_ini} ({ini_t}).")
    return errs


def validate_kardex_folio_and_serie(
    attrs: Dict[str, Any],
    *,
    instance: Any = None,
) -> Dict[str, Any]:
    from rest_framework.exceptions import ValidationError

    def _get(key: str) -> Any:
        if key in attrs:
            return attrs.get(key)
        return getattr(instance, key, None) if instance is not None else None

    field_errors: Dict[str, List[str]] = {}
    for ini_k, fin_k, li, lf in (
        ("folioini", "foliofin", "Folio inicial", "Folio final"),
        ("papelini", "papelfin", "Serie notarial inicial", "Serie notarial final"),
    ):
        errs = validate_folio_serie_pair(_get(ini_k), _get(fin_k), label_ini=li, label_fin=lf)
        if not errs:
            continue
        if any("no puede ser menor" in e for e in errs):
            field_errors[fin_k] = errs
        else:
            field_errors[ini_k] = errs
            field_errors[fin_k] = errs

    if field_errors:
        raise ValidationError(field_errors)
    return attrs
