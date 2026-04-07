from __future__ import annotations

from typing import Any, Dict, Optional
import time


class TTLCacheLite:
    def __init__(self, maxsize: int = 512, ttl_seconds: int = 600) -> None:
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._store: Dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None

        expires_at, value = item
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self.maxsize:
            oldest_key = next(iter(self._store.keys()))
            self._store.pop(oldest_key, None)
        self._store[key] = (time.time() + self.ttl_seconds, value)
