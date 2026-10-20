from datetime import date, datetime
from typing import Any, Optional


def format_pdt_writing_date(value: Any) -> Optional[str]:
    """Normalize kardex.fechaescritura (varchar or date) to YYYY-MM-DD."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if not text:
        return None
    sample = text[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(sample, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return sample
