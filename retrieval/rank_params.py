"""URL/query normalization for text result ranking modes."""

from __future__ import annotations

_ALLOWED_RANK_MODES = frozenset({"neutral", "raw", "llm"})
_DEFAULT_RANK_MODE = "neutral"


def normalize_rank_mode(raw: str | None) -> str:
    """Return ``neutral``, ``raw``, or ``llm`` (default ``neutral``)."""
    s = (raw or "").strip().lower()
    if s in _ALLOWED_RANK_MODES:
        return s
    if s in ("backend", "none", "off", "unfiltered"):
        return "raw"
    return _DEFAULT_RANK_MODE


def rank_mode_cache_segment(mode: str) -> str:
    m = normalize_rank_mode(mode)
    return f"|rm={m}"
