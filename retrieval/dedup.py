"""URL normalization, exact dedup, near-duplicate detection via embedding similarity."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from retrieval.embeddings import cosine_similarity, embed_text
from retrieval.types import NormalizedResult

_TRACKING_PARAMS = frozenset(
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


def normalize_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        scheme = (p.scheme or "http").lower()
        netloc = p.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = p.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        q = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
        ]
        q.sort()
        query = urlencode(q)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url.strip()


def fingerprint(result: NormalizedResult) -> str:
    raw = f"{normalize_url(result.url)}\n{result.title.lower().strip()}\n{result.snippet[:400].lower().strip()}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def deduplicate_results(
    results: list[NormalizedResult],
    *,
    near_dup_cosine: float = 0.92,
) -> list[NormalizedResult]:
    """Normalized URL exact match, then greedy drop if embedding cosine to kept set is high."""
    seen_urls: set[str] = set()
    kept_vecs: list[tuple[float, ...]] = []
    out: list[NormalizedResult] = []
    seen_fp: set[str] = set()

    for r in results:
        nu = normalize_url(r.url)
        if nu in seen_urls:
            continue
        fp = fingerprint(r)
        if fp in seen_fp:
            continue
        seen_fp.add(fp)

        doc = f"{r.title}\n{r.snippet}"[:1200]
        ev = embed_text(doc)
        if any(cosine_similarity(ev, kv) >= near_dup_cosine for kv in kept_vecs):
            continue
        seen_urls.add(nu)
        kept_vecs.append(ev)
        out.append(r)
    return out
