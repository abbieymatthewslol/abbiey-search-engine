"""Query–result intent alignment for ranking (lightweight heuristics, no extra network)."""

from __future__ import annotations

import os
import re

from retrieval.types import NormalizedResult

# Discussion / forum hosts: often rank for keyword overlap without matching navigational intent.
_FORUM_DISCUSSION_DOMAINS: tuple[str, ...] = (
    "news.ycombinator.com",
    "reddit.com",
    "old.reddit.com",
    "lobste.rs",
    "news.ycombinator.org",
    "quora.com",
)


def _truthy_intent_env() -> bool:
    raw = (os.environ.get("ABBIEY_INTENT_RANKING", "1") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _people_search_intent(query: str) -> bool:
    """User is looking for people-finder / directory services (not essays or travel blogs)."""
    ql = (query or "").lower()
    patterns = (
        r"\b(person|people)\s+search\b",
        r"\bpeople\s+finder\b",
        r"\b(person|people)\s+lookup\b",
        r"\bfind\s+(people|person|someone)\b",
        r"\bphone\s*book\b",
        r"\bwhite\s+pages?\b",
        r"\breverse\s+(phone|lookup)\b",
        r"\belectoral\s+roll\b",
    )
    return any(re.search(p, ql) for p in patterns)


def _doc_blob(result: NormalizedResult) -> str:
    return f"{result.title}\n{result.snippet}\n{result.url}\n{result.domain}".lower()


def _people_directory_signals(text: str) -> int:
    """Count how strongly the hit looks like a people-search product or directory page."""
    n = 0
    if re.search(r"\b(people|person)\s+(search|finder|lookup|directory)\b", text):
        n += 2
    if re.search(r"\bfree\s+.*\b(people|person)\b", text) and "finder" in text:
        n += 1
    if re.search(r"\b(reunion|white\s*pages?|reverse\s+lookup|phone\s*book)\b", text):
        n += 1
    if re.search(r"peoplesearch|whitepages|192\.com|anywho|peekyou|fastpeoplesearch", text):
        n += 2
    return n


def _is_forum_domain(domain: str) -> bool:
    d = (domain or "").lower()
    if d in _FORUM_DISCUSSION_DOMAINS:
        return True
    if d.endswith(".reddit.com") or d.endswith(".quora.com"):
        return True
    return False


def intent_alignment_delta(query: str, result: NormalizedResult) -> float:
    """
    Small additive adjustment to composite relevance score in [-0.18, 0.16].
    Keeps embeddings + authority but corrects obvious navigational mismatches.
    """
    if not _truthy_intent_env():
        return 0.0
    q = (query or "").strip()
    if not q:
        return 0.0

    if _people_search_intent(q):
        text = _doc_blob(result)
        sig = _people_directory_signals(text)
        if sig >= 2:
            return 0.14
        if sig == 1:
            return 0.07
        d = (result.domain or "").lower()
        if _is_forum_domain(d):
            # Keyword overlap (e.g. "Australia") is not enough for forum threads.
            return -0.15

    return 0.0
