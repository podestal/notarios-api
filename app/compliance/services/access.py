"""Ownership checks for compliance self-service endpoints."""

from __future__ import annotations

from typing import Optional

from notaria import models


def resolve_idusuario(user) -> int:
    """Django auth user PK is ``idusuario`` (see core.models.User)."""
    return int(getattr(user, "idusuario", None) or user.pk)


def kardex_owned_by_user(*, kardex: str, user) -> Optional[models.Kardex]:
    """
    Return the kardex row only if it belongs to the logged-in preparer.

    Returns None when the kardex does not exist or is owned by someone else
    (caller should respond with 404 to avoid leaking existence).
    """
    key = str(kardex or "").strip()
    if not key or user is None or not getattr(user, "is_authenticated", False):
        return None

    row = models.Kardex.objects.filter(kardex=key).first()
    if not row or row.idusuario is None:
        return None

    if int(row.idusuario) != resolve_idusuario(user):
        return None

    return row
