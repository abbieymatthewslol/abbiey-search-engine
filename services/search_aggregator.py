"""Merge, rank, cache — orchestrates ``search_sources`` for ``app._fetch_results``."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from cachetools import TTLCache

from services.search_sources import (
    search_brave,
    search_ddg,
    search_hn,
    search_reddit,
    search_searx,
    search_wikipedia,
)

logger = logging.getLogger(__name__)

_TRACK = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "_ga",
    }
)
_CACHE: TTLCache[str, list[dict]] = TTLCache(maxsize=512, ttl=60)
_SRC_W = {
    "ddg": 1.0,
    "wikipedia": 0.9,
    "brave": 1.1,
    "searxng": 0.85,
    "reddit": 0.7,
    "hackernews": 0.8,
}
_DOM = {
    "wikipedia.org": 0.25,
    "github.com": 0.15,
    "stackoverflow.com": 0.14,
    "news.ycombinator.com": 0.1,
    "reddit.com": 0.06,
}


def _normalize_agg_url(url: str) -> str:
    try:
        p = urlparse((url or "").strip())
        scheme = (p.scheme or "http").lower()
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in _TRACK]
        q.sort()
        return urlunparse((scheme, netloc, path, "", urlencode(q), ""))
    except Exception:
        return (url or "").strip()


def _kw_rel(q: str, title: str, snip: str) -> float:
    toks = [t for t in re.split(r"\W+", (q or "").lower()) if len(t) > 2][:12]
    if not toks:
        return 0.0
    blob = f"{title} {snip}".lower()
    hit = sum(1 for t in toks if t in blob)
    return min(0.6, 0.12 * hit)


def _fresh(ts: str | None) -> float:
    if not ts:
        return 0.0
    m = re.match(r"(\d{4}-\d{2}-\d{2})", ts)
    if not m:
        return 0.0
    try:
        d0 = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - d0).days
        return 0.18 if age <= 7 else (0.08 if age <= 30 else 0.0)
    except Exception:
        return 0.0


def _dom_q(url: str) -> float:
    try:
        h = urlparse(url).netloc.lower()
        if h.startswith("www."):
            h = h[4:]
        for k, v in _DOM.items():
            if h == k or h.endswith("." + k):
                return v
    except Exception:
        pass
    return 0.05


def _intent_mul(q: str) -> dict[str, float]:
    ql = (q or "").lower()
    m = {k: 1.0 for k in _SRC_W}
    if re.search(r"\b(how|what is|what are|who is|define|meaning of)\b", ql):
        m["wikipedia"] += 0.35
    if re.search(r"\b(latest|breaking|news|today|this week)\b", ql):
        m["reddit"] += 0.28
        m["hackernews"] += 0.28
    if re.search(r"\b(buy|price|cheap|coupon|deal|order|discount|shop)\b", ql):
        m["brave"] += 0.22
        m["ddg"] += 0.12
        m["searxng"] += 0.08
    return m


def _rank(rows: list[dict], user_query: str) -> list[dict]:
    mul = _intent_mul(user_query)
    seen: set[str] = set()
    scored: list[dict] = []
    for row in rows:
        u = _normalize_agg_url(row.get("url", ""))
        if not u or u in seen:
            continue
        seen.add(u)
        src = row.get("source") or "ddg"
        base = _SRC_W.get(src, 0.75) * mul.get(src, 1.0)
        fin = base + _kw_rel(user_query, row.get("title", ""), row.get("snippet", ""))
        fin += _fresh(row.get("timestamp"))
        fin += _dom_q(row.get("url", ""))
        row = dict(row)
        row["score"] = fin
        scored.append(row)
    scored.sort(key=lambda x: -x["score"])
    return scored


def _to_hits(rows: list[dict]) -> list[dict]:
    labels = {
        "ddg": "DuckDuckGo",
        "wikipedia": "Wikipedia",
        "brave": "Brave",
        "searxng": "SearXNG",
        "reddit": "Reddit",
        "hackernews": "Hacker News",
    }
    types = {
        "wikipedia": "encyclopedia",
        "reddit": "community",
        "hackernews": "community",
        "searxng": "aggregator",
        "brave": "web",
        "ddg": "web",
    }
    out: list[dict] = []
    for r in rows:
        src = r.get("source", "")
        hit = {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "body": r.get("snippet", ""),
            "source": labels.get(src, src.title()),
            "source_type": types.get(src, "web"),
        }
        if r.get("timestamp"):
            hit["date"] = r["timestamp"]
        out.append(hit)
    return out


async def _gather_all(
    user_query: str,
    effective_query: str,
    lang: str | None,
    ddg_fetcher: Callable[[], list],
) -> list[dict]:
    async def ddg_wrap() -> list[dict]:
        return await asyncio.to_thread(search_ddg, effective_query, ddg_fetcher=ddg_fetcher)

    wiki_lang = (lang or "en").strip() or "en"
    parts = await asyncio.gather(
        ddg_wrap(),
        search_wikipedia(effective_query, wiki_lang),
        search_brave(effective_query),
        search_searx(effective_query),
        search_reddit(effective_query),
        search_hn(effective_query),
        return_exceptions=True,
    )
    merged: list[dict] = []
    for p in parts:
        if isinstance(p, Exception):
            continue
        merged.extend(p or [])
    return _rank(merged, user_query)


def clear_aggregator_cache() -> None:
    _CACHE.clear()


def aggregate_text_search_sync(
    *,
    user_query: str,
    effective_query: str,
    ddg_fetcher: Callable[[], list],
    lang: str | None = None,
) -> list[dict]:
    """Flask hit dicts (``title``, ``url``, ``body``). Empty on failure."""
    qk = f"{effective_query}\x1f{lang or ''}"
    if qk in _CACHE:
        return list(_CACHE[qk])
    try:
        rows = asyncio.run(_gather_all(user_query, effective_query, lang, ddg_fetcher))
        hits = _to_hits(rows[:120])
        if hits:
            _CACHE[qk] = hits
        return hits
    except RuntimeError:
        logger.warning("search_aggregator asyncio.run failed", exc_info=True)
        return []
    except Exception:
        logger.debug("aggregate_text_search_sync failed", exc_info=True)
        return []
