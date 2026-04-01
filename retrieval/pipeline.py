"""End-to-end text retrieval: aggregate → dedup → score → cluster → hits."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Dict, List

from retrieval.aggregator import aggregate_sources
from retrieval.clustering import cluster_results
from retrieval.dedup import deduplicate_results
from retrieval.scoring import score_results
from retrieval.types import NormalizedResult, RetrievalParams

logger = logging.getLogger(__name__)


def query_time_sensitive(query: str) -> bool:
    ql = query.lower()
    hints = (
        "today",
        "tonight",
        "latest",
        "breaking",
        "news",
        "this week",
        "this month",
        "right now",
        "2024",
        "2025",
        "2026",
        "yesterday",
        "tomorrow",
    )
    return any(h in ql for h in hints)


def apply_pipeline_stages(
    user_query: str,
    effective_query: str,
    normalized: List[NormalizedResult],
    *,
    params: RetrievalParams,
) -> List[dict]:
    """Dedupe, score, truncate, cluster; return Flask hit dicts."""
    if not normalized:
        return []
    d = deduplicate_results(normalized)
    scored = score_results(
        effective_query,
        d,
        time_sensitive=query_time_sensitive(user_query),
    )
    top = scored[: max(1, params.top_n_after_score)]
    clustered = cluster_results(top)
    return [r.to_hit() for r in clustered]


async def run_text_retrieval_pipeline_async(
    *,
    user_query: str,
    effective_query: str,
    fetchers: Dict[str, Callable[[], list]],
    params: RetrievalParams,
) -> List[dict]:
    merged = await aggregate_sources(
        fetchers,
        effective_query,
        per_source_timeout=params.per_source_timeout,
        overall_timeout=params.overall_timeout,
    )
    # Interleave by source for diversity before dedupe: round-robin by source name
    by_src: Dict[str, List[NormalizedResult]] = {}
    for r in merged:
        by_src.setdefault(r.source, []).append(r)
    names = sorted(by_src.keys(), key=lambda k: (k != "ddg", k))
    rr: List[NormalizedResult] = []
    i = 0
    while len(rr) < len(merged):
        moved = False
        for name in names:
            bucket = by_src.get(name, [])
            if i < len(bucket):
                rr.append(bucket[i])
                moved = True
        if not moved:
            break
        i += 1
    return apply_pipeline_stages(user_query, effective_query, rr, params=params)


def run_text_retrieval_pipeline_sync(
    *,
    user_query: str,
    effective_query: str,
    fetchers: Dict[str, Callable[[], list]],
    max_results: int = 100,
    lang: str | None = None,
    region: str | None = None,
    time_filter: str | None = None,
    safesearch: str = "off",
) -> List[dict]:
    """Sync entry for Flask WSGI: runs asyncio event loop for one request."""
    params = RetrievalParams(
        max_results=max_results,
        lang=lang,
        region=region,
        time_filter=time_filter,
        safesearch=safesearch,
        time_sensitive_query=query_time_sensitive(user_query),
        top_n_after_score=min(max_results, 100),
        per_source_timeout=4.0,
        overall_timeout=9.0,
    )
    try:
        return asyncio.run(
            run_text_retrieval_pipeline_async(
                user_query=user_query,
                effective_query=effective_query,
                fetchers=fetchers,
                params=params,
            )
        )
    except RuntimeError as e:
        # Nested event loop (e.g. pytest-asyncio): fall back to a fresh loop
        msg = str(e).lower()
        if "running event loop" not in msg and "cannot be called from a running event loop" not in msg:
            raise
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                run_text_retrieval_pipeline_async(
                    user_query=user_query,
                    effective_query=effective_query,
                    fetchers=fetchers,
                    params=params,
                )
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)
