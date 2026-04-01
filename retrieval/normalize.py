"""Map raw upstream dicts to NormalizedResult."""

from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from retrieval.types import NormalizedResult


def _domain_from_url(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def _parse_published(raw: object) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    return None


def raw_dict_to_normalized(
    row: dict,
    *,
    source: str,
    rank: int,
) -> NormalizedResult | None:
    url = (row.get("url") or row.get("href") or "").strip()
    if not url:
        return None
    title = (row.get("title") or row.get("name") or url)[:500]
    snippet = (
        row.get("body")
        or row.get("snippet")
        or row.get("description")
        or row.get("text")
        or ""
    )
    if not isinstance(snippet, str):
        snippet = str(snippet)
    snippet = snippet[:2000]
    pub = _parse_published(row.get("date") or row.get("published") or row.get("pub_date"))
    domain = _domain_from_url(url)
    extra = {k: v for k, v in row.items() if k not in ("title", "url", "href", "body", "snippet")}
    return NormalizedResult(
        title=title,
        url=url,
        snippet=snippet,
        source=source,
        published_at=pub,
        domain=domain,
        raw_rank=rank,
        extra=extra,
    )


def normalized_list_from_raw(rows: list[dict], *, source: str) -> list[NormalizedResult]:
    out: list[NormalizedResult] = []
    for i, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        n = raw_dict_to_normalized(row, source=source, rank=i)
        if n:
            out.append(n)
    return out
