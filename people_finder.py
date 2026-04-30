"""People finder questionnaire: parse URL params, enrich search query, disclaimers."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote_plus, urlencode

# Short keys kept in URLs (GET form)
_PF_KEYS = (
    "city",
    "region",
    "country",
    "org",
    "aka",
    "intent",
    "era",
)

_INTENT_TERMS = {
    "social": ("social profiles", "linkedin OR facebook OR instagram OR x.com"),
    "professional": ("professional footprint", "linkedin OR crunchbase"),
    "news": ("news mentions", "news interview OR announcement"),
    "reunion": ("public directory reunion",),
    "general": (),
}


def parse_people_finder_args(args: Any) -> dict[str, str] | None:
    """Return normalized non-empty questionnaire fields from request.args-like mapping, or None if legacy."""
    out: dict[str, str] = {}
    for k in _PF_KEYS:
        raw = (args.get(f"pf_{k}") or "").strip()
        if not raw:
            continue
        out[k] = _sanitize_pf_value(k, raw)
    # Treat empty form submit as legacy (no narrowing)
    if not out:
        return None
    return out


def _sanitize_pf_value(key: str, val: str) -> str:
    val = " ".join(val.split())
    if key == "intent" and val not in _INTENT_TERMS:
        return "general"
    if len(val) > 280:
        val = val[:280].rstrip()
    return val


def build_people_finder_query_hint(base_query: str, pf: dict[str, str]) -> str:
    """Append structured hints to the user's name query for retrieval backends."""
    q = (base_query or "").strip()
    if not pf:
        return q
    parts = [q] if q else []
    geo = ", ".join(
        x
        for x in (
            pf.get("city"),
            pf.get("region"),
            pf.get("country"),
        )
        if x
    )
    if geo:
        parts.append(geo)
    if pf.get("aka"):
        parts.append(pf["aka"])
    if pf.get("org"):
        parts.append(pf["org"])
    if pf.get("era"):
        parts.append(pf["era"])

    intent = pf.get("intent") or "general"
    terms = _INTENT_TERMS.get(intent, ())
    if terms:
        parts.append(" ".join(terms))

    return " ".join(parts).strip() or q


def people_finder_cache_suffix(pf: dict[str, str] | None) -> str:
    if not pf:
        return ""
    try:
        payload = json.dumps(pf, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        payload = repr(sorted(pf.items()))
    # Keep cache keys bounded
    return "|pfv1:" + payload[:480]


def people_finder_banner_context(query: str, pf: dict[str, str]) -> dict[str, Any]:
    """Template context: summary line + disclaimer + outbound links."""
    hint = build_people_finder_query_hint(query, pf)
    lines = []
    geo = ", ".join(
        x for x in (pf.get("city"), pf.get("region"), pf.get("country")) if x
    )
    if geo:
        lines.append(f"Location context: {geo}.")
    if pf.get("org"):
        lines.append(f"Organization or school hint: {pf['org']}.")
    if pf.get("aka"):
        lines.append(f"Also searching for: {pf['aka']}.")

    qb = hint or query
    qp = quote_plus(qb)
    ql = qb[:80]

    outbound = [
        {"label": "DuckDuckGo (web)", "url": f"https://duckduckgo.com/?q={quote_plus(qb)}"},
        {"label": "Google (general web)", "url": f"https://www.google.com/search?q={quote_plus(qb)}"},
        {"label": "OpenCorporates (companies)", "url": f"https://opencorporates.com/companies?q={quote_plus(qb)}"},
    ]

    return {
        "summary_line": " · ".join(lines) if lines else None,
        "effective_hint": hint,
        "disclaimer": (
            "People search aggregates public-web and structured sources. Someone may not appear here because "
            "they use a private name spelling, rarely appear online, have removed profiles, or because indexes "
            "are incomplete or delayed. abbiey.search does not access non-public databases, court records paid "
            "aggregators without your own subscription, or offline-only directories."
        ),
        "qf_query_preview": ql,
        "qf_params": {f"pf_{k}": v for k, v in pf.items()},
    }


def build_people_search_params(
    query: str,
    region: str = "",
    cleanweb: bool = False,
    pf: dict[str, str] | None = None,
) -> dict[str, str]:
    """Flattened GET params for /search type=people with optional questionnaire fields."""
    p: dict[str, str] = {"q": query or "", "type": "people"}
    if region:
        p["region"] = region
    if cleanweb:
        p["cleanweb"] = "1"
    if pf:
        for k, v in pf.items():
            if v:
                p[f"pf_{k}"] = v
    return p


def append_pf_query_string(query: str, region: str, cleanweb: bool, pf: dict[str, str] | None) -> str:
    """Return '&pf_city=…' fragment for appending after base search URL."""
    qs = urlencode(build_people_search_params(query, region=region, cleanweb=cleanweb, pf=pf), safe="")
    return "&" + qs if qs else ""


def people_pf_params_only_fragment(pf: dict[str, str] | None) -> str:
    """'&pf_city=…' only (for URLs that already include q= and type=)."""
    if not pf:
        return ""
    enc = urlencode({f"pf_{k}": v for k, v in pf.items() if v}, safe="")
    return "&" + enc if enc else ""


def enrich_people_engine_query(engine_query: str, pf: dict[str, str] | None) -> str:
    """Apply questionnaire hints onto the resolved engine query (after operators merge)."""
    eq = (engine_query or "").strip()
    if not pf:
        return eq
    return build_people_finder_query_hint(eq, pf)
