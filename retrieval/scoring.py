"""Composite scoring: freshness, domain authority, semantic (local embeddings)."""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from typing import Iterable

from retrieval.embeddings import cosine_similarity, embed_text
from retrieval.intent import intent_alignment_delta
from retrieval.types import NormalizedResult

# Tunable weights (env override)
def _weights() -> tuple[float, float, float]:
    def f(key: str, default: str) -> float:
        try:
            return float(os.environ.get(key, default))
        except ValueError:
            return float(default)

    return (
        f("ABBIEY_SCORE_W_FRESHNESS", "0.25"),
        f("ABBIEY_SCORE_W_AUTHORITY", "0.35"),
        f("ABBIEY_SCORE_W_SEMANTIC", "0.40"),
    )


DOMAIN_SCORES: dict[str, float] = {
    "wikipedia.org": 0.95,
    "en.wikipedia.org": 0.95,
    "github.com": 0.9,
    "stackoverflow.com": 0.88,
    "stackexchange.com": 0.85,
    "arxiv.org": 0.92,
    "nih.gov": 0.9,
    "nature.com": 0.88,
    "reuters.com": 0.86,
    "bbc.co.uk": 0.84,
    "bbc.com": 0.84,
    "medium.com": 0.6,
    "reddit.com": 0.55,
    "news.ycombinator.com": 0.72,
}

_SPAM_HINTS = ("casino", "viagra", "torrent", "crack", "warez")


def authority_score(domain: str) -> float:
    d = (domain or "").lower()
    if any(h in d for h in _SPAM_HINTS):
        return 0.15
    for key, score in DOMAIN_SCORES.items():
        if d == key or d.endswith("." + key):
            return score
    return 0.5


def freshness_score(published_at: datetime | None, *, time_sensitive: bool, decay_days: float = 45.0) -> float:
    if published_at is None:
        return 0.35 if time_sensitive else 0.55
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        pub = published_at.replace(tzinfo=timezone.utc)
    else:
        pub = published_at.astimezone(timezone.utc)
    age_days = max(0.0, (now - pub).total_seconds() / 86400.0)
    k = decay_days / 2.0 if time_sensitive else decay_days
    return float(math.exp(-age_days / max(k, 1e-6)))


def semantic_score(query: str, result: NormalizedResult) -> float:
    qv = embed_text(query)
    doc = f"{result.title}\n{result.snippet}"[:1500]
    dv = embed_text(doc)
    return max(0.0, min(1.0, (cosine_similarity(qv, dv) + 1.0) / 2.0))


def score_results(query: str, results: Iterable[NormalizedResult], *, time_sensitive: bool) -> list[NormalizedResult]:
    w_f, w_a, w_s = _weights()
    total_w = w_f + w_a + w_s
    if total_w <= 0:
        total_w = 1.0
    ranked: list[tuple[float, NormalizedResult]] = []
    for r in results:
        fsc = freshness_score(r.published_at, time_sensitive=time_sensitive)
        asc = authority_score(r.domain)
        ssc = semantic_score(query, r)
        base = (w_f * fsc + w_a * asc + w_s * ssc) / total_w
        # Slight boost for earlier raw_rank within same source (stability)
        tie = 1.0 / (1.0 + r.raw_rank * 0.02)
        adj = intent_alignment_delta(query, r)
        final = min(1.0, max(0.0, base * tie + adj))
        ranked.append((final, r))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in ranked]
