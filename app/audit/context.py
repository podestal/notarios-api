import threading
from contextlib import contextmanager
from typing import Any, Iterator

_local = threading.local()


def set_actor(user: Any = None, source: str = "") -> None:
    user_id = None
    username = ""
    if user is not None and getattr(user, "is_authenticated", False):
        user_id = getattr(user, "idusuario", None) or getattr(user, "pk", None)
        username = getattr(user, "username", "") or ""
    _local.user_id = int(user_id) if user_id not in (None, "") else None
    _local.username = str(username)
    _local.source = source or ""


def get_actor() -> dict:
    return {
        "user_id": getattr(_local, "user_id", None),
        "username": getattr(_local, "username", "") or "",
        "source": getattr(_local, "source", "") or "",
    }


def clear_actor() -> None:
    _local.user_id = None
    _local.username = ""
    _local.source = ""


def set_source(source: str) -> None:
    _local.source = source or ""


def is_audit_suppressed() -> bool:
    return bool(getattr(_local, "audit_suppressed", False))


@contextmanager
def suppress_audit() -> Iterator[None]:
    """Skip kardex change logs for internal cleanup (leftover rows, retries)."""
    previous = getattr(_local, "audit_suppressed", False)
    _local.audit_suppressed = True
    try:
        yield
    finally:
        _local.audit_suppressed = previous
