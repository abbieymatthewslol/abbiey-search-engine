"""
User-defined search bots: allowlisted HTTP crawl and plain-text extraction.

No arbitrary code execution — only GET fetches to user-approved hostnames, with
SSRF guards and size limits. Pages are stored for keyword search in /search.
Supports HTML and text, plus JSON / NDJSON dataset responses that embed https URLs.
"""

from __future__ import annotations

import csv
import io
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
# Per-page timeout. 6s keeps 3 fetches under Vercel's default 10s limit so a
# full crawl step never overruns a serverless invocation.
HTTP_TIMEOUT = 6.0
# Default chunk size for chunked/resumable crawls. Full crawls still happen
# one step at a time via crawl_bot_pages_step until the queue drains.
DEFAULT_PAGES_PER_INVOCATION = 3
_MAX_JSON_URLS_PER_PAGE = 80

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


def parse_json_documents(raw: str) -> list[Any]:
    """Single JSON value or newline-delimited JSON (NDJSON)."""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        return [json.loads(raw)]
    except Exception:
        pass
    docs: list[Any] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            docs.append(json.loads(line))
        except Exception:
            continue
    return docs


def parse_csv_rows(
    raw: str, *, max_rows: int = 200, max_cols: int = 30, max_len_each: int = 400
) -> list[list[str]]:
    raw = (raw or "").strip()
    if not raw:
        return []
    stream = io.StringIO(raw)
    try:
        sample = raw[:4000]
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except Exception:
        dialect = csv.excel
    out: list[list[str]] = []
    try:
        reader = csv.reader(stream, dialect)
        for row in reader:
            if len(out) >= max_rows:
                break
            cleaned: list[str] = []
            for cell in row[:max_cols]:
                s = str(cell).strip()[:max_len_each]
                if s:
                    cleaned.append(s)
            if cleaned:
                out.append(cleaned)
    except Exception:
        return []
    return out


def collect_http_urls_from_tabular(rows: list[list[str]], cap: int = _MAX_JSON_URLS_PER_PAGE) -> list[str]:
    acc: list[str] = []
    for row in rows:
        for cell in row:
            if len(acc) >= cap:
                return acc
            s = (cell or "").strip()
            if s.startswith("http://") or s.startswith("https://"):
                if s not in acc:
                    acc.append(s)
    return acc


def snippet_from_tabular(rows: list[list[str]], cap: int = MAX_SNIPPET) -> str:
    parts: list[str] = []
    total = 0
    for row in rows:
        for cell in row:
            if total >= cap:
                break
            s = (cell or "").strip()
            if not s or s.startswith("http://") or s.startswith("https://"):
                continue
            s = re.sub(r"\s+", " ", s).strip()[:600]
            if not s:
                continue
            parts.append(s)
            total += len(s) + 1
        if total >= cap:
            break
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return text[:cap]


def collect_http_urls_from_json(obj: Any, cap: int = _MAX_JSON_URLS_PER_PAGE) -> list[str]:
    """Recursively collect unique http(s) URL strings (for dataset / API index pages)."""
    acc: list[str] = []

    def walk(o: Any) -> None:
        if len(acc) >= cap:
            return
        if isinstance(o, str):
            s = o.strip()
            if s.startswith("http://") or s.startswith("https://"):
                if s not in acc:
                    acc.append(s)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return acc


def snippet_from_json_values(obj: Any, cap: int = MAX_SNIPPET) -> str:
    """Flatten string values from JSON for keyword search (no URLs)."""
    parts: list[str] = []

    def walk(o: Any) -> None:
        if sum(len(p) for p in parts) >= cap:
            return
        if isinstance(o, str):
            s = o.strip()
            if not s or s.startswith("http://") or s.startswith("https://"):
                return
            parts.append(s[:600])
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    return text[:cap]


def _title_from_dataset_url(url: str) -> str:
    try:
        path = urlparse(url).path or ""
        seg = path.rstrip("/").split("/")[-1] or urlparse(url).netloc
        return seg.strip()[:MAX_TITLE] or "Dataset"
    except Exception:
        return "Dataset"


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


def crawl_bot_pages_step(
    queue: list[tuple[str, int]],
    seen: list[str] | set[str],
    allow_hosts: list[str],
    max_depth: int,
    max_pages: int,
    pages_per_invocation: int = DEFAULT_PAGES_PER_INVOCATION,
) -> tuple[list[dict[str, str]], list[tuple[str, int]], list[str], str | None]:
    """Resume a chunked BFS crawl.

    Returns ``(new_pages, remaining_queue, new_seen, error)``. When
    ``remaining_queue`` is empty the job is done. Caller persists
    ``new_seen`` (deduped URLs) + the remaining queue between invocations.

    ``pages_per_invocation`` hard-caps how many fresh pages are fetched in this
    step so a single serverless call cannot run longer than roughly
    ``pages_per_invocation * HTTP_TIMEOUT`` seconds.
    """
    if not allow_hosts:
        return [], [], list(seen), "No allowed hosts configured."
    max_depth = max(0, min(int(max_depth), 2))
    max_pages = max(1, min(int(max_pages), 30))
    pages_per_invocation = max(1, min(int(pages_per_invocation), max_pages))

    seen_set: set[str] = set(seen or [])
    results: list[dict[str, str]] = []
    q: list[tuple[str, int]] = list(queue or [])
    pages_this_step = 0

    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    }

    with httpx.Client(
        headers=headers,
        follow_redirects=True,
        timeout=HTTP_TIMEOUT,
        limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
    ) as client:
        while q and pages_this_step < pages_per_invocation and len(seen_set) < max_pages * 20:
            url, depth = q.pop(0)
            if url in seen_set:
                continue
            seen_set.add(url)
            pages_this_step += 1
            try:
                pu = urlparse(url)
                host = (pu.hostname or "").lower()
                if not host_allowed_for_bot(host, allow_hosts):
                    continue
                r = client.get(url)
                if r.status_code >= 400:
                    continue
                ct = (r.headers.get("content-type") or "").lower()
                body = r.content
                if not body or len(body) > MAX_PAGE_BYTES:
                    continue

                path_l = (pu.path or "").lower().split("?")[0].rstrip("/")
                looks_json = "json" in ct or "application/ld+json" in ct or path_l.endswith(".json")
                looks_jsonl = (
                    "ndjson" in ct
                    or "jsonl" in ct
                    or path_l.endswith(".ndjson")
                    or path_l.endswith(".jsonl")
                    or path_l.endswith(".jsonlines")
                )
                looks_csv = (
                    "text/csv" in ct
                    or "application/csv" in ct
                    or "text/tab-separated-values" in ct
                    or path_l.endswith(".csv")
                    or path_l.endswith(".tsv")
                )
                if looks_json or looks_jsonl:
                    try:
                        text = body.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    docs = parse_json_documents(text)
                    if not docs:
                        continue
                    merged_for_walk: Any = docs[0] if len(docs) == 1 else docs
                    urls_found: list[str] = []
                    for d in docs:
                        for u in collect_http_urls_from_json(d):
                            if u not in urls_found:
                                urls_found.append(u)
                    snip = snippet_from_json_values(merged_for_walk)
                    if not snip and urls_found:
                        snip = "Links: " + " ".join(urls_found[:20])[:MAX_SNIPPET]
                    title = _title_from_dataset_url(url)
                    results.append({"url": url, "title": title, "snippet": snip or title})

                    if depth >= max_depth:
                        continue
                    for u in urls_found:
                        joined = u.split("#")[0]
                        n = normalize_http_seed(joined, allow_hosts)
                        if n and n not in seen_set and len(seen_set) + len(q) < max_pages * 20:
                            q.append((n, depth + 1))
                    continue
                if looks_csv:
                    try:
                        text = body.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    rows = parse_csv_rows(text)
                    if not rows:
                        continue
                    urls_found = collect_http_urls_from_tabular(rows)
                    snip = snippet_from_tabular(rows)
                    if not snip and urls_found:
                        snip = "Links: " + " ".join(urls_found[:20])[:MAX_SNIPPET]
                    title = _title_from_dataset_url(url)
                    results.append({"url": url, "title": title, "snippet": snip or title})

                    if depth >= max_depth:
                        continue
                    for u in urls_found:
                        joined = u.split("#")[0]
                        n = normalize_http_seed(joined, allow_hosts)
                        if n and n not in seen_set and len(seen_set) + len(q) < max_pages * 20:
                            q.append((n, depth + 1))
                    continue

                if "html" not in ct and "text/plain" not in ct and "application/xhtml" not in ct:
                    continue
                soup = BeautifulSoup(body, "html.parser")
                title = _extract_title(soup) or host
                snippet = _visible_text_from_soup(soup)[:MAX_SNIPPET]
                results.append({"url": url, "title": title, "snippet": snippet})

                if depth >= max_depth:
                    continue
                for a in soup.find_all("a", href=True):
                    if len(q) + len(results) > max_pages * 8:
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
                    if norm not in seen_set and len(seen_set) + len(q) < max_pages * 20:
                        q.append((norm, depth + 1))
            except Exception as exc:
                logger.debug("crawl skip url=%s err=%s", url, exc)

    return results, q, sorted(seen_set), None


def crawl_bot_pages(
    seed_urls: list[str],
    allow_hosts: list[str],
    max_depth: int,
    max_pages: int,
) -> tuple[list[dict[str, str]], str | None]:
    """Back-compat wrapper: run a full synchronous crawl (no checkpointing).

    Only used by legacy tests / CLI. Production uses ``crawl_bot_pages_step``
    with persisted queue+seen state so a long crawl is resumable across
    serverless invocations.
    """
    if not allow_hosts:
        return [], "No allowed hosts configured."
    seeds: list[str] = []
    for s in seed_urls or []:
        n = normalize_http_seed(s, allow_hosts)
        if n:
            seeds.append(n)
    if not seeds:
        return [], "No valid seed URLs for the allowed hosts."

    queue: list[tuple[str, int]] = [(u, 0) for u in seeds]
    seen: list[str] = []
    all_pages: list[dict[str, str]] = []

    # Step until the queue drains or we hit max_pages.
    while queue and len(all_pages) < max(1, min(int(max_pages), 30)):
        step_pages, queue, seen, err = crawl_bot_pages_step(
            queue=queue,
            seen=seen,
            allow_hosts=allow_hosts,
            max_depth=max_depth,
            max_pages=max_pages,
            pages_per_invocation=max(1, min(int(max_pages), 30)),
        )
        if err:
            return all_pages, err
        all_pages.extend(step_pages)
        if not step_pages and not queue:
            break

    if not all_pages:
        return [], "Crawl found no indexable pages (check seeds, robots, or timeouts)."
    return all_pages, None
