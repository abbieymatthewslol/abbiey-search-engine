"""Simple per-source circuit breaker (fail-open after cooldown)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    cooldown_seconds: float = 60.0
    _failures: int = 0
    _opened_until: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self) -> bool:
        with self._lock:
            if time.monotonic() < self._opened_until:
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_until = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_until = time.monotonic() + self.cooldown_seconds
                self._failures = 0


_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def breaker_for(name: str) -> CircuitBreaker:
    with _breakers_lock:
        if name not in _breakers:
            _breakers[name] = CircuitBreaker()
        return _breakers[name]
