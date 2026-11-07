"""
Request-scoped memo for SISGEN / UIF / PDT collectors.

Stage services each call the same collectors. On the kardex list that meant
3–4 identical validations per row. One shared cache per summarize() keeps the
results identical while cutting the work.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

_CacheKey = Tuple[str, str]
_active: ContextVar[Optional["CollectorCache"]] = ContextVar(
    "compliance_collector_cache", default=None
)


class CollectorCache:
    def __init__(self) -> None:
        self._data: Dict[_CacheKey, Any] = {}
        self._lock = threading.Lock()

    def get_or_set(self, kind: str, kardex: str, factory: Callable[[], Any]) -> Any:
        key: _CacheKey = (kind, str(kardex or "").strip())
        with self._lock:
            if key in self._data:
                return self._data[key]
        value = factory()
        with self._lock:
            existing = self._data.get(key)
            if existing is not None:
                return existing
            self._data[key] = value
            return value


@contextmanager
def collector_cache_scope(cache: Optional[CollectorCache] = None) -> Iterator[CollectorCache]:
    store = cache or CollectorCache()
    token = _active.set(store)
    try:
        yield store
    finally:
        _active.reset(token)


def cached_call(kind: str, kardex: str, factory: Callable[[], Any]) -> Any:
    store = _active.get()
    if store is None:
        return factory()
    return store.get_or_set(kind, kardex, factory)
