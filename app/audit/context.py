import threading
from typing import Any

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
