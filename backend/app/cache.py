"""Small, self-contained, thread-safe TTL cache — no external dependency.

FastAPI runs `def` (non-async) endpoints in a threadpool, so concurrent
requests can call `get_or_load` at once — every read/write of the internal
store is guarded by a `threading.Lock`. Uses `time.monotonic()`, never
`time.time()`: a wall-clock adjustment (NTP sync, DST) must never make a
cache entry look older or younger than it actually is.

FAIL CLOSED (ADR-0020 + ADR-0026 — see app.sap): `loader()` runs OUTSIDE the
lock (so a slow DB call never blocks other keys/requests), and its exception
is never caught here — it always propagates straight to the caller, and the
failed value is never written to the store. `ttl_seconds <= 0` disables
caching outright (`loader()` runs on every call) — the settings/test
kill-switch path (`Settings.sap_cache_ttl_seconds = 0`).
"""
import threading
import time
from collections.abc import Callable, Hashable
from typing import Generic, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    """Generic key -> (loaded_at, value) store. `ttl_seconds` is passed per
    call (not fixed at construction) so a caller can read it fresh from
    settings every time, without needing to reconstruct the cache when
    settings change (e.g. between tests)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[Hashable, tuple[float, V]] = {}

    def get_or_load(self, key: Hashable, ttl_seconds: float, loader: Callable[[], V]) -> V:
        """Return the cached value for `key` if it was loaded less than
        `ttl_seconds` ago; otherwise call `loader()`, store the result, and
        return it. A `loader()` exception propagates unchanged and is never
        stored — the previous (now stale) entry, if any, is left untouched
        but is never served as a substitute for the failed call."""
        if ttl_seconds <= 0:
            return loader()

        now = time.monotonic()
        with self._lock:
            cached = self._store.get(key)
            if cached is not None and (now - cached[0]) < ttl_seconds:
                return cached[1]

        value = loader()

        with self._lock:
            self._store[key] = (now, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
