"""
Normalized OSINT fact shape (JSON-serializable dicts).

Each fact is one observable claim from a whitelisted public source.
"""

from __future__ import annotations

from typing import Any, TypedDict


class OsintFact(TypedDict, total=False):
    """Single normalized observation."""

    type: str  # e.g. dns_a, dns_mx, rdap_status, ptr
    label: str  # human-readable section title
    value: str  # primary payload (IP, hostname, status line, etc.)
    source: str  # short attribution ("DNS via Cloudflare DoH", "RDAP")
    observed_at: str  # ISO 8601 UTC
    confidence: float  # 0.0–1.0
    evidence_url: str | None  # link to public registry or spec, if any
    detail: str | None  # optional extra line (truncated upstream)


def fact(
    *,
    type: str,
    label: str,
    value: str,
    source: str,
    observed_at: str,
    confidence: float = 0.85,
    evidence_url: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Build a fact dict with required fields."""
    out: dict[str, Any] = {
        "type": type,
        "label": label,
        "value": value,
        "source": source,
        "observed_at": observed_at,
        "confidence": confidence,
    }
    if evidence_url is not None:
        out["evidence_url"] = evidence_url
    if detail is not None:
        out["detail"] = detail
    return out
