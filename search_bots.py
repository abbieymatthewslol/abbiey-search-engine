"""
User-defined search bots: allowlisted HTTP crawl and plain-text extraction.

No arbitrary code execution — only GET fetches to user-approved hostnames, with
SSRF guards and size limits. Pages are stored for keyword search in /search.
"""

from __future__ import annotations

import json
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_UA = "abbiey.search/bot (+https://www.abbieysearch.com)"
MAX_PAGE_BYTES = 1_400_000
MAX_SNIPPET = 2000
MAX_TITLE = 400
HTTP_TIMEOUT = 12.0

_BLOCKED_HOST_FRAGMENTS = (
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.",
    "metadata.google.internal",
    "metadata.google",
    ".local",
    "kubernetes.default",
)


def parse_json_list(raw: Any, *, max_items: int, max_len_each: int) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            items = json.loads(raw)
        except Exception:
            return []
    else:
        return []
    out: list[str] = []
    for x in items[:max_items]:
        s = str(x).strip()[:max_len_each]
        if s and s not in out:
            out.append(s)
    return out


def _host_blocked(host: str) -> bool:
    h = (host or "").lower().rstrip(".")
    if not h or h.isdigit():
        return True
    for frag in _BLOCKED_HOST_FRAGMENTS:
        if frag in h:
            return True
    return False


def host_allowed_for_bot(host: str, allow_hosts: list[str]) -> bool:
    host = (host or "").lower().rstrip(".")
    if _host_blocked(host):
        return False
    for pat in allow_hosts:
        p = (pat or "").lower().strip().lstrip(".").rstrip(".")
        if not p:
            continue
        if host == p or host.endswith("." + p):
            return True
    return False


def normalize_http_seed(url: str, allow_hosts: list[str]) -> str | None:
    u = (url or "").strip()
    if len(u) > 2000:
        return None
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc or _host_blocked(parsed.hostname or ""):
        return None
    if not host_allowed_for_bot(parsed.hostname or "", allow_hosts):
        return None
    return u


def _visible_text_from_soup(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    return text[:8000]


def _extract_title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        t = str(og["content"]).strip()
        if t:
            return t[:MAX_TITLE]
    if soup.title and soup.title.string:
        return str(soup.title.string).strip()[:MAX_TITLE]
    return ""


def crawl_bot_pages(
    seed_urls: list[str],
    allow_hosts: list[str],
    max_depth: int,
    max_pages: int,
) -> tuple[list[dict[str, str]], str | None]:
    """
    BFS crawl within allow_hosts. Returns list of {url, title, snippet} and optional error.
    """
    if not allow_hosts:
        return [], "No allowed hosts configured."
    max_depth = max(0, min(int(max_depth), 2))
    max_pages = max(1, min(int(max_pages), 30))

    seeds: list[str] = []
    for s in seed_urls:
        n = normalize_http_seed(s, allow_hosts)
        if n:
            seeds.append(n)
    if not seeds:
        return [], "No valid seed URLs for the allowed hosts."

    seen: set[str] = set()
    results: list[dict[str, str]] = []
    queue: list[tuple[str, int]] = [(u, 0) for u in seeds]

    headers = {"User-Agent": DEFAULT_UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}

    with httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=HTTP_TIMEOUT,
        limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
    ) as client:
        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            try:
                pu = urlparse(url)
                host = (pu.hostname or "").lower()
                if not host_allowed_for_bot(host, allow_hosts):
                    continue
                r = client.get(url)
                if r.status_code >= 400:
                    continue
                ct = (r.headers.get("content-type") or "").lower()
                if "html" not in ct and "text/plain" not in ct and "application/xhtml" not in ct:
                    continue
                body = r.content
                if not body or len(body) > MAX_PAGE_BYTES:
                    continue
                soup = BeautifulSoup(body, "html.parser")
                title = _extract_title(soup) or host
                snippet = _visible_text_from_soup(soup)[:MAX_SNIPPET]
                results.append({"url": url, "title": title, "snippet": snippet})

                if depth >= max_depth:
                    continue
                for a in soup.find_all("a", href=True):
                    if len(queue) + len(results) > max_pages * 8:
                        break
                    href = (a.get("href") or "").strip()
                    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                        continue
                    joined = urljoin(url, href)
                    pj = urlparse(joined)
                    if pj.scheme not in ("http", "https"):
                        continue
                    nh = (pj.hostname or "").lower()
                    if not host_allowed_for_bot(nh, allow_hosts):
                        continue
                    norm = joined.split("#")[0]
                    if norm not in seen and len(seen) + len(queue) < max_pages * 20:
                        queue.append((norm, depth + 1))
            except Exception as exc:
                logger.debug("crawl skip url=%s err=%s", url, exc)

    if not results:
        return [], "Crawl found no indexable pages (check seeds, robots, or timeouts)."
    return results, None
