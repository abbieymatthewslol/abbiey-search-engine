from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse


class ProtocolDepth:
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


_RAW_HOST_PATTERNS = (
    re.compile(r"(^|\.)reddit\.com$", re.I),
    re.compile(r"(^|\.)news\.ycombinator\.com$", re.I),
    re.compile(r"(^|\.)x\.com$", re.I),
    re.compile(r"(^|\.)twitter\.com$", re.I),
    re.compile(r"(^|\.)facebook\.com$", re.I),
    re.compile(r"(^|\.)tiktok\.com$", re.I),
    re.compile(r"(^|\.)4chan\.org$", re.I),
    re.compile(r"(^|\.)stackexchange\.com$", re.I),
    re.compile(r"(^|\.)stackoverflow\.com$", re.I),
    re.compile(r"(^|\.)quora\.com$", re.I),
)

_REFERENCE_HOST_PATTERNS = (
    re.compile(r"(^|\.)wikipedia\.org$", re.I),
    re.compile(r"(^|\.)britannica\.com$", re.I),
)

_PRIMARY_HOST_PATTERNS = (
    re.compile(r"(^|\.)\.gov$", re.I),
    re.compile(r"(^|\.)\.edu$", re.I),
    re.compile(r"(^|\.)who\.int$", re.I),
    re.compile(r"(^|\.)un\.org$", re.I),
    re.compile(r"(^|\.)oecd\.org$", re.I),
    re.compile(r"(^|\.)worldbank\.org$", re.I),
    re.compile(r"(^|\.)europa\.eu$", re.I),
    re.compile(r"(^|\.)nih\.gov$", re.I),
    re.compile(r"(^|\.)ncbi\.nlm\.nih\.gov$", re.I),
    re.compile(r"(^|\.)pubmed\.ncbi\.nlm\.nih\.gov$", re.I),
    re.compile(r"(^|\.)cdc\.gov$", re.I),
    re.compile(r"(^|\.)nejm\.org$", re.I),
    re.compile(r"(^|\.)science\.org$", re.I),
    re.compile(r"(^|\.)nature\.com$", re.I),
    re.compile(r"(^|\.)thelancet\.com$", re.I),
)

_SECONDARY_HOST_PATTERNS = (
    re.compile(r"(^|\.)reuters\.com$", re.I),
    re.compile(r"(^|\.)apnews\.com$", re.I),
    re.compile(r"(^|\.)bbc\.co\.uk$", re.I),
    re.compile(r"(^|\.)bbc\.com$", re.I),
    re.compile(r"(^|\.)theguardian\.com$", re.I),
    re.compile(r"(^|\.)nytimes\.com$", re.I),
    re.compile(r"(^|\.)washingtonpost\.com$", re.I),
    re.compile(r"(^|\.)wsj\.com$", re.I),
    re.compile(r"(^|\.)economist\.com$", re.I),
    re.compile(r"(^|\.)ft\.com$", re.I),
    re.compile(r"(^|\.)arxiv\.org$", re.I),
)

_SEO_SPAM_RE = re.compile(
    r"\b(top\s*\d+|best\s+|coupon|promo\s*code|casino|slots|betting|free\s+download|crack\b|torrent\b)\b",
    re.I,
)

_LIKELY_NEWS_RE = re.compile(r"\b(breaking|news|today|latest|live)\b", re.I)


@dataclass(frozen=True)
class ProtocolSource:
    index: int
    title: str
    url: str
    hostname: str
    tier: str
    published_at: datetime | None
    retrieved_at: datetime
    excerpt: str
    unverified: bool


def _safe_hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def classify_source_tier(*, url: str, hostname: str | None = None) -> tuple[str, bool]:
    h = (hostname or _safe_hostname(url) or "").lower()
    if not h:
        return "Secondary", False

    for pat in _REFERENCE_HOST_PATTERNS:
        if pat.search(h):
            return "Reference", False

    for pat in _RAW_HOST_PATTERNS:
        if pat.search(h):
            return "Raw", True

    for pat in _PRIMARY_HOST_PATTERNS:
        if pat.search(h):
            return "Primary", False

    for pat in _SECONDARY_HOST_PATTERNS:
        if pat.search(h):
            return "Secondary", False

    if h.endswith(".gov") or h.endswith(".edu"):
        return "Primary", False

    return "Secondary", False


def _parse_datetimeish(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(s[: len(fmt)], fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _is_seo_spam(title: str, excerpt: str) -> bool:
    text = f"{title} {excerpt}".strip()
    if not text:
        return False
    return bool(_SEO_SPAM_RE.search(text))


def _query_seems_historical(query: str) -> bool:
    q = (query or "").lower()
    if any(k in q for k in ("history", "historical", "timeline", "in ")):
        return True
    if re.search(r"\b(19\d{2}|20\d{2})\b", q):
        return True
    return False


def _hit_looks_news_like(query: str, title: str, url: str) -> bool:
    if _LIKELY_NEWS_RE.search(title or ""):
        return True
    u = (url or "").lower()
    if any(x in u for x in ("/news", "news.")):
        return True
    if any(x in (query or "").lower() for x in ("news", "latest", "today")):
        return True
    return False


def _is_outdated(*, query: str, published_at: datetime | None, title: str, url: str) -> bool:
    if not published_at:
        return False
    if _query_seems_historical(query):
        return False
    now = datetime.now(timezone.utc)
    years = (now - published_at).days / 365.25
    threshold = 5.0 if _hit_looks_news_like(query, title, url) else 10.0
    return years > threshold


def protocol_sources_from_hits(query: str, hits: list[dict], *, cleanweb: bool = False) -> tuple[list[ProtocolSource], dict]:
    retrieved_at = datetime.now(timezone.utc)

    seen: set[str] = set()
    sources: list[ProtocolSource] = []
    excluded = {"duplicate": 0, "outdated": 0, "seo_spam": 0, "invalid": 0}
    for hit in hits or []:
        if not isinstance(hit, dict):
            excluded["invalid"] += 1
            continue
        url = (hit.get("url") or "").strip()
        if not url:
            excluded["invalid"] += 1
            continue
        if url in seen:
            excluded["duplicate"] += 1
            continue
        seen.add(url)

        title = (hit.get("title") or "").strip()
        hostname = (hit.get("hostname") or "").strip().lower() or _safe_hostname(url)
        excerpt = (hit.get("body") or hit.get("snippet") or "").strip()
        if len(excerpt) > 360:
            excerpt = excerpt[:360].rsplit(" ", 1)[0] + "…"

        published_at = _parse_datetimeish(hit.get("published_at") or hit.get("date") or hit.get("published"))
        if _is_outdated(query=query, published_at=published_at, title=title, url=url):
            excluded["outdated"] += 1
            continue
        if cleanweb and _is_seo_spam(title, excerpt):
            excluded["seo_spam"] += 1
            continue

        tier, unverified = classify_source_tier(url=url, hostname=hostname)
        sources.append(
            ProtocolSource(
                index=len(sources) + 1,
                title=title[:300],
                url=url[:900],
                hostname=hostname[:260],
                tier=tier,
                published_at=published_at,
                retrieved_at=retrieved_at,
                excerpt=excerpt,
                unverified=unverified,
            )
        )

    if not sources and hits:
        for hit in hits[:6]:
            url = (hit.get("url") or "").strip()
            if not url:
                continue
            title = (hit.get("title") or "").strip()
            hostname = (hit.get("hostname") or "").strip().lower() or _safe_hostname(url)
            excerpt = (hit.get("body") or hit.get("snippet") or "").strip()
            if len(excerpt) > 360:
                excerpt = excerpt[:360].rsplit(" ", 1)[0] + "…"
            tier, unverified = classify_source_tier(url=url, hostname=hostname)
            sources.append(
                ProtocolSource(
                    index=len(sources) + 1,
                    title=title[:300],
                    url=url[:900],
                    hostname=hostname[:260],
                    tier=tier,
                    published_at=_parse_datetimeish(hit.get("published_at") or hit.get("date") or hit.get("published")),
                    retrieved_at=retrieved_at,
                    excerpt=excerpt,
                    unverified=unverified,
                )
            )
        excluded["invalid"] = max(excluded["invalid"], 0)

    return sources, excluded


def protocol_render_superscript_citations(text: str, *, max_sources: int) -> str:
    if not text:
        return ""

    def _repl(m: re.Match) -> str:
        n = int(m.group(1))
        if n < 1 or n > max_sources:
            return m.group(0)
        return f"<sup>[{n}](#source-{n})</sup>"

    out = re.sub(r"\[(\d{1,3})\]", _repl, text)
    out = re.sub(r"\[\^(\d{1,3})\^\]", _repl, out)
    return out


def sanitize_harmful_instructions(markdown: str) -> str:
    if not markdown:
        return ""
    if re.search(r"(?mi)^\s*(step\s*\d+\b|\d+\.)\s+", markdown):
        cleaned = re.sub(r"(?ms)^\s*(step\s*\d+\b|\d+\.)\s+.*?$", "", markdown)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if cleaned:
            return cleaned + "\n\n> Note: Procedural instructions were removed; this response stays at a high-level overview.\n"
        return (
            "## DIRECT\n"
            "High-level overview only; procedural instructions were removed. (Confidence: 0.25)\n"
        )
    return markdown


def protocol_detect_harmful_query(query: str) -> dict:
    q = (query or "").lower()
    self_harm = bool(re.search(r"\b(suicide|kill myself|self[- ]harm|want to die)\b", q))
    illegal = bool(re.search(r"\b(build a bomb|make a bomb|how to hack|credit card dump|meth|heroin|buy fake id)\b", q))
    violence = bool(re.search(r"\b(shooting|massacre|kill them|how to murder)\b", q))
    return {
        "self_harm": self_harm,
        "illegal": illegal,
        "violence": violence,
        "context_warning": self_harm or illegal or violence,
    }


def build_protocol_sources_section(sources: list[ProtocolSource]) -> str:
    def _fmt_dt(dt: datetime | None) -> str:
        if not dt:
            return ""
        try:
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""

    groups: dict[str, list[ProtocolSource]] = {"Primary": [], "Secondary": [], "Reference": [], "Raw": []}
    for s in sources:
        groups.setdefault(s.tier, []).append(s)

    lines: list[str] = []
    lines.append("## Evidence Hierarchy")

    def _render_list(title: str, items: list[ProtocolSource]) -> None:
        if not items:
            return
        lines.append(f"### {title}")
        for s in items:
            published = _fmt_dt(s.published_at)
            retrieved = _fmt_dt(s.retrieved_at)
            tags = []
            tags.append(f"Tier: {s.tier}")
            if s.unverified:
                tags.append("unverified")
            if published:
                tags.append(f"Published: {published}")
            if retrieved:
                tags.append(f"Retrieved: {retrieved}")
            tag_str = "; ".join(tags)
            lines.append(f"{s.index}. <a id=\"source-{s.index}\"></a>[{s.title or s.hostname}]({s.url}) ({s.hostname}) — {tag_str}")
            if s.excerpt:
                lines.append(f"    - Excerpt: {s.excerpt}")

    _render_list("Primary", groups.get("Primary") or [])
    _render_list("Secondary", groups.get("Secondary") or [])
    _render_list("Reference", groups.get("Reference") or [])

    raw_items = groups.get("Raw") or []
    if raw_items:
        lines.append("### See also community discussion")
        lines.append("<details><summary>Unverified raw sources</summary>")
        lines.append("")
        for s in raw_items:
            retrieved = _fmt_dt(s.retrieved_at)
            tag_str = f"Tier: Raw; unverified; Retrieved: {retrieved}" if retrieved else "Tier: Raw; unverified"
            lines.append(f"{s.index}. <a id=\"source-{s.index}\"></a>[{s.title or s.hostname}]({s.url}) ({s.hostname}) — {tag_str}")
            if s.excerpt:
                lines.append(f"    - Excerpt: {s.excerpt}")
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines).strip() + "\n"


def build_protocol_methodology_line(*, searched: int, synthesized: int, excluded: dict) -> str:
    parts = []
    if excluded.get("duplicate"):
        parts.append(f"excluded {excluded['duplicate']} duplicate")
    if excluded.get("outdated"):
        parts.append(f"excluded {excluded['outdated']} outdated")
    if excluded.get("seo_spam"):
        parts.append(f"excluded {excluded['seo_spam']} SEO/spam")
    if excluded.get("invalid"):
        parts.append(f"skipped {excluded['invalid']} invalid")
    tail = ("; " + ", ".join(parts)) if parts else ""
    return f"Searched {searched} sources, synthesized {synthesized}{tail}."


def build_protocol_markdown(*, answer_block_markdown: str, sources: list[ProtocolSource], methodology: str, safety: dict) -> str:
    out: list[str] = []
    if safety.get("context_warning"):
        out.append("> Context warning: This query matches harm/illegal-activity patterns. The answer avoids procedural instructions and focuses on high-level, safety- and legality-aware context.")
        out.append("")

    triage_counts: dict[str, int] = {"Primary": 0, "Secondary": 0, "Reference": 0, "Raw": 0}
    for s in sources:
        triage_counts[s.tier] = triage_counts.get(s.tier, 0) + 1
    out.append("## Source Triage")
    out.append(
        "- "
        + ", ".join(
            [
                f"Primary: {triage_counts.get('Primary', 0)}",
                f"Secondary: {triage_counts.get('Secondary', 0)}",
                f"Reference: {triage_counts.get('Reference', 0)}",
                f"Raw (unverified): {triage_counts.get('Raw', 0)}",
            ]
        )
    )
    out.append("")

    out.append(answer_block_markdown.strip())
    out.append("")
    out.append("## Traceability")
    out.append(f"- Methodology: {methodology}")
    out.append("- Inference vs direct evidence: Any inference is labeled explicitly as inference in the text.")
    out.append("")
    out.append(build_protocol_sources_section(sources))
    return "\n".join(out).strip() + "\n"

