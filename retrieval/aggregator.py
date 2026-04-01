"""Fan-out / fan-in aggregation with per-source timeouts and circuit breaker."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Dict, List

from retrieval.circuit import breaker_for
from retrieval.normalize import normalized_list_from_raw
from retrieval.types import NormalizedResult

logger = logging.getLogger(__name__)


class CallableAdapter:
    """Wraps a sync zero-arg callable returning list[dict] (existing app fetchers)."""

    def __init__(self, name: str, fn: Callable[[], list]):
        self.name = name
        self._fn = fn

    async def search(self, query: str, params: dict) -> List[NormalizedResult]:
        br = breaker_for(self.name)
        if not br.allow():
            logger.debug("retrieval circuit open for %s", self.name)
            return []
        per_timeout = float(params.get("per_source_timeout") or 4.0)
        try:
            raw = await asyncio.wait_for(asyncio.to_thread(self._fn), timeout=per_timeout)
            br.record_success()
        except asyncio.TimeoutError:
            logger.warning("retrieval timeout source=%s", self.name)
            br.record_failure()
            return []
        except Exception:
            logger.warning("retrieval failed source=%s", self.name, exc_info=True)
            br.record_failure()
            return []
        return normalized_list_from_raw(list(raw or []), source=self.name)


async def aggregate_sources(
    fetchers: Dict[str, Callable[[], list]],
    query: str,
    *,
    per_source_timeout: float = 4.0,
    overall_timeout: float = 9.0,
) -> List[NormalizedResult]:
    """Run all adapters concurrently; merge into one pool (order: completion interleave via extend)."""
    if not fetchers:
        return []

    params = {"per_source_timeout": per_source_timeout}
    adapters = [CallableAdapter(name, fn) for name, fn in fetchers.items()]

    async def _gather() -> List[NormalizedResult]:
        tasks = [a.search(query, params) for a in adapters]
        done = await asyncio.gather(*tasks, return_exceptions=True)
        merged: List[NormalizedResult] = []
        for a, part in zip(adapters, done):
            if isinstance(part, Exception):
                logger.warning("retrieval gather error source=%s", a.name, exc_info=True)
                continue
            merged.extend(part)
        return merged

    try:
        return await asyncio.wait_for(_gather(), timeout=overall_timeout)
    except asyncio.TimeoutError:
        logger.warning("retrieval overall timeout after %.1fs", overall_timeout)
        return []
