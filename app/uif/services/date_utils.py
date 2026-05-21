from datetime import date, datetime
from typing import Tuple

from rest_framework import status
from rest_framework.response import Response


def parse_date_range(
    initial_date: str, final_date: str
) -> Tuple[date, date] | Response:
    """Parse DD/MM/YYYY or YYYY-MM-DD date pair; return Response on error."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            start = datetime.strptime(initial_date, fmt).date()
            end = datetime.strptime(final_date, fmt).date()
            return start, end
        except ValueError:
            continue
    return Response(
        {"error": "Invalid date format. Use DD/MM/YYYY or YYYY-MM-DD"},
        status=status.HTTP_400_BAD_REQUEST,
    )
