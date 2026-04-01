"""Canonical types for the retrieval layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Protocol, runtime_checkable


@dataclass
class NormalizedResult:
    """Unified result shape for all upstream sources."""

    title: str
    url: str
    snippet: str
    source: str
    published_at: datetime | None
    domain: str
    raw_rank: int
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_hit(self) -> dict:
        """Flask / frontend hit dict (uses ``body`` for snippet text)."""
        hit = {
            "title": self.title or "",
            "url": self.url or "",
            "body": self.snippet or "",
        }
        for k, v in self.extra.items():
            if k not in hit:
                hit[k] = v
        return hit


@runtime_checkable
class SourceAdapter(Protocol):
    """Async adapter contract (implemented with ``async def search``)."""

    name: str

    async def search(self, query: str, params: dict) -> List[NormalizedResult]:
        ...


@dataclass
class RetrievalParams:
    """Tunables passed through the pipeline."""

    max_results: int = 100
    lang: str | None = None
    region: str | None = None
    time_filter: str | None = None
    safesearch: str = "off"
    time_sensitive_query: bool = False
    top_n_after_score: int = 100
    per_source_timeout: float = 4.0
    overall_timeout: float = 9.0
