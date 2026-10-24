"""Thread-safe in-memory cache where every entry expires after a fixed TTL.
The HTTP server handles requests on several threads, so access is locked."""

import threading
import time
from typing import Any


class Cache:
    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry[1]:
                del self._entries[key]
                return None
            return entry[0]

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._entries[key] = (value, time.monotonic() + self._ttl)
