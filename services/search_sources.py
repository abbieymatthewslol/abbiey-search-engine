"""Per-source fetchers — async httpx + sync DDG via injected ``ddg_fetcher``."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)
UA = "abbiey.search/1.0 (+https://www.abbieysearch.com/)"
_SEARX = (
    "https://search.mdosch.de",
    "https://searx.be",
    "https://searxng.site",
    "https://search.disroot.org",
)


def _std(
    title: str,
    url: str,
    snippet: str,
    source: str,
    score: float = 0.0,
    timestamp: str | None = None,
) -> dict[str, Any]:
    return {
        "title": (title or "")[:500],
        "url": (url or "").strip(),
        "snippet": (snippet or "")[:2000],
        "source": source,
        "score": float(score),
        "timestamp": timestamp,
    }


def search_ddg(query: str, *, ddg_fetcher: Callable[[], list]) -> list[dict]:
    del query
    rows: list[dict] = []
    try:
        for r in ddg_fetcher() or []:
            if not isinstance(r, dict):
                continue
            u = (r.get("url") or r.get("href") or "").strip()
            if not u:
                continue
            sn = r.get("body") or r.get("snippet") or ""
            rows.append(_std(r.get("title") or u, u, str(sn), "ddg"))
    except Exception:
        logger.debug("search_ddg failed", exc_info=True)
    return rows


async def search_wikipedia(query: str, lang: str = "en") -> list[dict]:
    base = f"https://{(lang or 'en').strip() or 'en'}.wikipedia.org/w/api.php"
    rows: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=4.0, headers={"User-Agent": UA}) as c:
            r = await c.get(
                base,
                params={
                    "action": "opensearch",
                    "search": query,
                    "limit": "8",
                    "namespace": "0",
                    "format": "json",
                },
            )
            r.raise_for_status()
            data = r.json()
            if len(data) >= 4:
                for i in range(min(len(data[1]), len(data[3]))):
                    rows.append(
                        _std(data[1][i], data[3][i], (data[2][i] if i < len(data[2]) else "") or "", "wikipedia")
                    )
    except Exception:
        logger.debug("search_wikipedia failed", exc_info=True)
    return rows


async def search_brave(query: str, n: int = 12) -> list[dict]:
    key = (os.environ.get("BRAVE_API_KEY") or os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip()
    if not key:
        return []
    rows: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=4.0, headers={"User-Agent": UA, "X-Subscription-Token": key}) as c:
            r = await c.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max(1, min(n, 20))},
            )
            if r.status_code >= 400:
                return []
            for it in (r.json() or {}).get("web", {}).get("results", []) or []:
                u = (it.get("url") or "").strip()
                if not u:
                    continue
                rows.append(
                    _std(
                        it.get("title") or u,
                        u,
                        (it.get("description") or "")[:2000],
                        "brave",
                        timestamp=(it.get("age") or None),
                    )
                )
    except Exception:
        logger.debug("search_brave failed", exc_info=True)
    return rows


async def search_searx(query: str, n: int = 15) -> list[dict]:
    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=4.0, headers={"User-Agent": UA}) as c:
        for base in _SEARX:
            try:
                r = await c.get(
                    f"{base}/search",
                    params={"q": query, "format": "json", "categories": "general"},
                )
                if r.status_code != 200:
                    continue
                for it in (r.json() or {}).get("results", [])[:n]:
                    u = (it.get("url") or "").strip()
                    if not u:
                        continue
                    rows.append(_std(it.get("title") or u, u, it.get("content") or "", "searxng"))
                if rows:
                    break
            except Exception:
                continue
    return rows


async def search_reddit(query: str, n: int = 12) -> list[dict]:
    rows: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=4.0, headers={"User-Agent": UA}) as c:
            r = await c.get(
                "https://www.reddit.com/search.json",
                params={"q": query, "sort": "relevance", "limit": min(n, 25), "type": "link"},
            )
            r.raise_for_status()
            for ch in (r.json() or {}).get("data", {}).get("children", []) or []:
                p = ch.get("data") or {}
                u = (p.get("url") or "").strip()
                t = (p.get("title") or "").strip()
                if not u or not t:
                    continue
                st = (p.get("selftext") or "")[:180]
                if st and st not in ("[deleted]", "[removed]"):
                    sn = st
                else:
                    sn = f"{p.get('subreddit_name_prefixed', '')} · {p.get('score', 0)} upvotes"
                created = None
                if p.get("created_utc"):
                    created = datetime.fromtimestamp(int(p["created_utc"]), tz=timezone.utc).strftime("%Y-%m-%d")
                rows.append(_std(t, u, sn, "reddit", timestamp=created))
    except Exception:
        logger.debug("search_reddit failed", exc_info=True)
    return rows


async def search_hn(query: str, n: int = 10) -> list[dict]:
    rows: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=4.0, headers={"User-Agent": UA}) as c:
            r = await c.get(
                "https://hn.algolia.com/api/v1/search",
                params={"query": query, "hitsPerPage": min(n, 20)},
            )
            r.raise_for_status()
            for h in (r.json() or {}).get("hits", []) or []:
                u = (h.get("url") or "").strip() or f"https://news.ycombinator.com/item?id={h.get('objectID', '')}"
                t = (h.get("title") or "").strip()
                if not t:
                    continue
                ts = (h.get("created_at") or "")[:10] or None
                sn = f"{h.get('points', 0)} pts · {h.get('num_comments', 0)} comments"
                rows.append(_std(t, u, sn, "hackernews", timestamp=ts))
    except Exception:
        logger.debug("search_hn failed", exc_info=True)
    return rows
