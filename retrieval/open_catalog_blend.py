"""Blend free public catalogs (Wikidata, OpenAlex, Crossref) for extra web hits.

Used when ``open_knowledge=1`` on text search. All endpoints are keyless and
documented for polite use with a descriptive User-Agent.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

_UD = {"User-Agent": "abbiey.search/1.0 (open catalog; +https://abbieysearch.com)"}

_WIKI_API = "https://www.wikidata.org/w/api.php"
_OPENALEX = "https://api.openalex.org/works"
_CROSSREF = "https://api.crossref.org/works"


def _http_get(url: str, *, params: dict[str, Any] | None = None, timeout: float = 5.0):
    try:
        import httpx
    except ImportError:
        return None
    try:
        return httpx.get(url, params=params or {}, headers=_UD, timeout=timeout)
    except Exception:
        logger.debug("open_catalog_http_failed url=%s", url[:80], exc_info=True)
        return None


def _wikidata_hits(q: str, limit: int = 5) -> list[dict]:
    if not (q or "").strip():
        return []
    resp = _http_get(
        _WIKI_API,
        params={
            "action": "wbsearchentities",
            "search": q[:280],
            "language": "en",
            "limit": min(limit, 8),
            "format": "json",
            "origin": "*",
        },
        timeout=4.5,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        rows = resp.json().get("search") or []
    except Exception:
        return []
    hits: list[dict] = []
    ids = [r.get("id") for r in rows if r.get("id")]
    sitelinks: dict[str, str] = {}
    if ids:
        r2 = _http_get(
            _WIKI_API,
            params={
                "action": "wbgetentities",
                "ids": "|".join(ids[:8]),
                "props": "sitelinks",
                "format": "json",
                "origin": "*",
            },
            timeout=4.5,
        )
        if r2 is not None and r2.status_code == 200:
            try:
                entities = (r2.json().get("entities") or {}).items()
                for eid, ent in entities:
                    sl = (ent or {}).get("sitelinks") or {}
                    en = sl.get("enwiki")
                    if en and en.get("title"):
                        t = en["title"].replace(" ", "_")
                        sitelinks[eid] = f"https://en.wikipedia.org/wiki/{quote(t)}"
            except Exception:
                pass

    for r in rows:
        eid = r.get("id") or ""
        if not eid:
            continue
        label = (r.get("label") or "").strip() or eid
        desc = (r.get("description") or "").strip()
        url = sitelinks.get(eid) or f"https://www.wikidata.org/wiki/{eid}"
        body = desc if desc else "Wikidata entity"
        hits.append({
            "title": label,
            "url": url,
            "body": body[:500],
            "source": "Wikidata",
        })
    return hits


def _openalex_blurb(inv_index: dict | None) -> str:
    """Reconstruct a short abstract from OpenAlex inverted index."""
    if not inv_index:
        return ""
    max_i = -1
    flat: list[tuple[int, str]] = []
    for word, positions in inv_index.items():
        if not isinstance(positions, list):
            continue
        for pish in positions:
            try:
                i = int(pish)
            except (TypeError, ValueError):
                continue
            flat.append((i, word))
            if i > max_i:
                max_i = i
    if max_i < 0:
        return ""
    buf = [""] * (max_i + 1)
    for i, word in flat:
        buf[i] = word
    text = " ".join(buf)
    return re.sub(r"\s+", " ", text).strip()[:400]


def _openalex_hits(q: str, limit: int = 5) -> list[dict]:
    if not (q or "").strip():
        return []
    resp = _http_get(
        _OPENALEX,
        params={
            "search": q[:300],
            "per-page": min(limit, 8),
            "mailto": "search@abbieysearch.com",
        },
        timeout=5.0,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        results = resp.json().get("results") or []
    except Exception:
        return []
    hits: list[dict] = []
    for w in results:
        title = (w.get("display_name") or "").strip()
        if not title:
            continue
        url = ""
        loc = w.get("best_oa_location") or {}
        if isinstance(loc, dict):
            url = (loc.get("landing_page_url") or loc.get("pdf_url") or "").strip()
        if not url:
            pl = w.get("primary_location") or {}
            if isinstance(pl, dict):
                src = pl.get("source") or {}
                home = (src.get("homepage_url") or "").rstrip("/") if isinstance(src, dict) else ""
                doi = (w.get("doi") or "").strip()
                if doi:
                    url = doi if doi.startswith("http") else f"https://doi.org/{doi}"
                elif home and pl.get("is_oa"):
                    url = home
        if not url:
            oid = (w.get("id") or "").replace("https://openalex.org/", "")
            if oid:
                url = f"https://openalex.org/{oid}"
        blurb = _openalex_blurb(w.get("abstract_inverted_index"))
        if not blurb:
            iw = w.get("ids") or {}
            if isinstance(iw, dict):
                dois = iw.get("doi")
                if dois and isinstance(dois, str):
                    blurb = dois
        hits.append({
            "title": title,
            "url": url,
            "body": blurb or "OpenAlex work",
            "source": "OpenAlex",
            "source_type": "academic",
        })
    return hits


def _crossref_lite_hits(q: str, limit: int = 4) -> list[dict]:
    if not (q or "").strip():
        return []
    resp = _http_get(
        _CROSSREF,
        params={
            "query": q[:280],
            "rows": min(limit, 6),
            "select": "DOI,title,container-title,author,published-print,abstract",
        },
        timeout=5.0,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        items = resp.json().get("message", {}).get("items") or []
    except Exception:
        return []
    hits: list[dict] = []
    for item in items:
        titles = item.get("title", [])
        title = titles[0] if titles else ""
        if not title:
            continue
        doi = item.get("DOI", "")
        url = f"https://doi.org/{doi}" if doi else ""
        if not url:
            continue
        abstract = re.sub(r"<[^>]+>", "", item.get("abstract", "") or "").strip()[:280]
        authors = item.get("author", [])
        author_str = ", ".join(
            f"{a.get('family', '')}".strip()
            for a in authors[:2]
        )
        pub = (item.get("container-title") or [""])[0]
        body = abstract if abstract else " · ".join(filter(None, [author_str, pub]))
        hits.append({
            "title": title,
            "url": url,
            "body": body,
            "source": "Crossref",
            "source_type": "academic",
        })
    return hits


def fetch_open_knowledge_hits(query: str, *, max_total: int = 12) -> list[dict]:
    """Return deduped hit dicts (title, url, body, source) from public catalogs."""
    q = (query or "").strip()
    if not q:
        return []
    wd = _wikidata_hits(q, limit=5)
    oa = _openalex_hits(q, limit=4)
    cr = _crossref_lite_hits(q, limit=3)
    merged = wd + oa + cr
    seen: set[str] = set()
    out: list[dict] = []
    for h in merged:
        u = (h.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(h)
        if len(out) >= max_total:
            break
    if out:
        logger.info("open_knowledge_blend: %d hits for q.len=%d", len(out), len(q))
    return out
