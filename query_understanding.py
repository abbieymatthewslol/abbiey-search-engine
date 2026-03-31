"""
Query preprocessing: synonym normalization, rule-based intent classification,
and pattern parsing for local / navigational phrasing.

Designed to run before entity detection; expand with ML later if needed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# --- Synonyms: informal / regional / slang → canonical English phrase (lowercase) ---
SYNONYM_MAP: Dict[str, str] = {
    # Retail / places (AU/NZ/UK → neutral)
    "op shop": "thrift store",
    "op shops": "thrift stores",
    "opp shop": "thrift store",
    "charity shop": "thrift store",
    "charity shops": "thrift stores",
    "jumble sale": "yard sale",
    "car boot sale": "yard sale",
    "boot sale": "yard sale",
    "servo": "gas station",
    "servos": "gas stations",
    "petrol station": "gas station",
    "petrol stations": "gas stations",
    "filling station": "gas station",
    "bottle shop": "liquor store",
    "bottle-o": "liquor store",
    "off licence": "liquor store",
    "off license": "liquor store",
    "newsagent": "newsstand",
    "newsagents": "newsstands",
    "takeaway": "takeout",
    "take-away": "takeout",
    "chippy": "fish and chips restaurant",
    "chippie": "fish and chips restaurant",
    "chemist": "pharmacy",
    "chemists": "pharmacies",
    "surgery": "doctor office",
    "gp surgery": "doctor office",
    "car park": "parking lot",
    "car parks": "parking lots",
    "multi-storey car park": "parking garage",
    "lolly shop": "candy store",
    "milk bar": "convenience store",
    "corner shop": "convenience store",
    "corner store": "convenience store",
    "dairy": "convenience store",
    "smoko": "coffee break",
    "footpath": "sidewalk",
    "nappy": "diaper",
    "nappies": "diapers",
    "pram": "stroller",
    "pushchair": "stroller",
    "flat": "apartment",
    "flats": "apartments",
    "lift": "elevator",
    "lifts": "elevators",
    "rubbish bin": "trash can",
    "wheelie bin": "trash can",
    "bin": "trash can",
    "cashpoint": "atm",
    "cash machine": "atm",
    "hole in the wall": "atm",
    "motorway": "highway",
    "dual carriageway": "divided highway",
    "roundabout": "traffic circle",
    "zebra crossing": "crosswalk",
    "takeaway coffee": "coffee to go",
    "brekkie": "breakfast",
    "arvo": "afternoon",
    "maccas": "mcdonalds",
    "maccies": "mcdonalds",
    "mcdonald's": "mcdonalds",
}

# Canonical surface phrase → internal category key (for entity extraction)
PLACE_CATEGORY_PHRASES: Dict[str, str] = {
    "thrift store": "thrift_store",
    "thrift stores": "thrift_store",
    "secondhand store": "thrift_store",
    "second hand store": "thrift_store",
    "second-hand store": "thrift_store",
    "gas station": "gas_station",
    "gas stations": "gas_station",
    "liquor store": "liquor_store",
    "pharmacy": "pharmacy",
    "pharmacies": "pharmacy",
    "doctor office": "medical_clinic",
    "parking lot": "parking",
    "parking lots": "parking",
    "parking garage": "parking",
    "candy store": "candy_store",
    "convenience store": "convenience_store",
    "convenience stores": "convenience_store",
    "fish and chips restaurant": "restaurant",
    "newsstand": "newsstand",
    "takeout": "takeout_restaurant",
    "atm": "atm",
    "coffee to go": "cafe",
    "yard sale": "yard_sale",
    "restaurant": "restaurant",
    "cafe": "cafe",
    "coffee shop": "cafe",
    "supermarket": "grocery_store",
    "grocery store": "grocery_store",
    "bakery": "bakery",
    "hotel": "hotel",
    "hostel": "hostel",
    "library": "library",
    "museum": "museum",
    "park": "park",
    "playground": "playground",
    "gym": "gym",
    "hospital": "hospital",
    "dentist": "dentist",
    "bank": "bank",
    "post office": "post_office",
}


@dataclass
class PatternParse:
    """Structured slots from common query shapes."""

    kind: str  # closest, near_me, best_in, near_poi
    head: Optional[str] = None
    subject: Optional[str] = None
    location: Optional[str] = None
    unknown_subject: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("extra", None)
        if self.extra:
            d["extra"] = dict(self.extra)
        return {k: v for k, v in d.items() if v is not None or k == "kind"}


@dataclass
class PreprocessedQuery:
    original: str
    normalized: str
    synonyms_applied: List[Tuple[str, str]]
    intent: str
    pattern: Optional[PatternParse]
    unknown_terms: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original": self.original,
            "normalized": self.normalized,
            "synonyms_applied": [{"from": a, "to": b} for a, b in self.synonyms_applied],
            "intent": self.intent,
            "pattern": self.pattern.to_dict() if self.pattern else None,
            "unknown_terms": self.unknown_terms,
        }


def normalize_synonyms(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Replace known informal phrases with canonical forms (longest first)."""
    if not text or not text.strip():
        return text, []
    result = text
    applied: List[Tuple[str, str]] = []
    for informal, canonical in sorted(SYNONYM_MAP.items(), key=lambda kv: len(kv[0]), reverse=True):
        # Word-boundary safe: avoid splitting inside longer tokens
        pat = re.compile(r"(?<![\w-])" + re.escape(informal) + r"(?![\w-])", re.IGNORECASE)

        def _sub(m: re.Match) -> str:
            return canonical

        new_result, n = pat.subn(_sub, result)
        if n:
            applied.append((informal, canonical))
            result = new_result
    return result, applied


_LOCAL_HINTS = re.compile(
    r"\b("
    r"near\s+me|nearby|close\s+to\s+me|closest|nearest|around\s+here|"
    r"walking\s+distance|open\s+now|hours\s+today|directions\s+to|"
    r"how\s+far|in\s+my\s+area|local\b"
    r")\b",
    re.I,
)
_TRANSACTIONAL_HINTS = re.compile(
    r"\b("
    r"buy|purchase|order\s+online|price|cost\s+of|cheap(est)?|deal|coupon|"
    r"discount|promo\s+code|subscribe|subscription|booking|book\s+a|"
    r"tickets|checkout|cart|shipping|delivery\s+fee|refund|warranty"
    r")\b",
    re.I,
)
_NAV_HINTS = re.compile(
    r"\b("
    r"login|log\s*in|sign\s*in|signin|signup|sign\s*up|register|"
    r"official\s+(site|website)|homepage|home\s+page|www\.|\.com/login|"
    r"customer\s+portal|dashboard"
    r")\b",
    re.I,
)
_SHORT_DOMAINISH = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
    r"|^[a-z0-9][a-z0-9.-]{1,40}\.(com|org|net|io|co|app|dev)$",
    re.I,
)


def classify_intent(normalized: str, original: str) -> str:
    """Rule-based intent: local_search | navigational | informational | transactional."""
    s = (normalized or "").strip()
    o = (original or "").strip()
    if not s:
        return "informational"
    if _TRANSACTIONAL_HINTS.search(s):
        return "transactional"
    compact = s.replace(" ", "")
    if _NAV_HINTS.search(s) or (
        " " not in s and len(s) < 45 and _SHORT_DOMAINISH.match(compact)
    ):
        return "navigational"
    if _LOCAL_HINTS.search(s) or _LOCAL_HINTS.search(o):
        return "local_search"
    return "informational"


def parse_query_patterns(normalized: str) -> Optional[PatternParse]:
    """Extract slots from common templates (runs on synonym-normalized text)."""
    s = (normalized or "").strip()
    if not s:
        return None
    sl = s.lower().strip()

    m = re.match(r"^(best|top|good|cheap(?:est)?)\s+(.+?)\s+in\s+(.+)$", sl)
    if m:
        return PatternParse(
            kind="best_in",
            head=m.group(1).lower(),
            subject=m.group(2).strip(),
            location=m.group(3).strip(),
        )

    m = re.match(r"^(closest|nearest)\s+(.+)$", sl, re.I)
    if m:
        return PatternParse(
            kind="closest",
            head=m.group(1).lower(),
            subject=m.group(2).strip(),
        )

    m = re.match(r"^(.+?)\s+near\s+me$", sl, re.I)
    if m:
        subj = m.group(1).strip()
        return PatternParse(kind="near_me", subject=subj)

    m = re.match(r"^(.+?)\s+near\s+(.+)$", sl, re.I)
    if m:
        loc = m.group(2).strip()
        if loc.lower() != "me":
            return PatternParse(
                kind="near_poi",
                subject=m.group(1).strip(),
                location=loc,
            )

    return None


def _collect_unknown_place_hints(
    normalized: str, pattern: Optional[PatternParse]
) -> List[str]:
    """Subjects from patterns that do not contain a known place-category phrase."""
    unknown: List[str] = []
    if not pattern or not pattern.subject:
        return unknown
    c = pattern.subject.strip()
    if len(c) < 2 or len(c) > 80 or re.search(r"^\d", c):
        return unknown
    cl = c.lower()
    matched = False
    for phrase in PLACE_CATEGORY_PHRASES:
        if phrase in cl:
            matched = True
            break
    if not matched:
        unknown.append(c)
    return unknown


def place_category_matches(text: str) -> List[Dict[str, str]]:
    """Non-overlapping matches of known place phrases in normalized text."""
    normalized_lower = (text or "").lower()
    n = len(normalized_lower)
    if not n:
        return []
    covered = [False] * n
    results: List[Dict[str, str]] = []
    for phrase in sorted(PLACE_CATEGORY_PHRASES.keys(), key=len, reverse=True):
        pat = re.compile(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", re.I)
        for m in pat.finditer(normalized_lower):
            s, e = m.start(), m.end()
            if s >= e or any(covered[s:e]):
                continue
            for i in range(s, e):
                covered[i] = True
            results.append(
                {
                    "surface": m.group(0),
                    "category_key": PLACE_CATEGORY_PHRASES[phrase],
                    "canonical_phrase": phrase,
                }
            )
    return results


def preprocess_query(query: str) -> PreprocessedQuery:
    """Full pipeline: synonyms → intent → patterns → unknown hints."""
    original = query if query else ""
    normalized, synonyms_applied = normalize_synonyms(original.strip())
    intent = classify_intent(normalized, original)
    pattern = parse_query_patterns(normalized)
    unknown_terms = _collect_unknown_place_hints(normalized, pattern)
    return PreprocessedQuery(
        original=original.strip(),
        normalized=normalized.strip(),
        synonyms_applied=synonyms_applied,
        intent=intent,
        pattern=pattern,
        unknown_terms=unknown_terms,
    )


_SUMMARY_EXPLANATORY = re.compile(
    r"\b("
    r"explain|definition|meaning of|tutorial|guide|learn about|"
    r"difference between|compared to|overview of|facts about|how does|how do|"
    r"why does|why do|what is|what are|what does|who is|who are"
    r")\b",
    re.I,
)
_QUESTION_START = re.compile(
    r"^(what|why|how|when|where|who|which|is|are|does|do|can|could|should|would|did|have|has|had)\b",
    re.I,
)


def has_informational_summary_signals(text: str) -> bool:
    """Question-shaped or explanatory phrasing suitable for an AI web summary."""
    s = (text or "").strip()
    if not s:
        return False
    if "?" in s:
        return True
    if _SUMMARY_EXPLANATORY.search(s):
        return True
    if _QUESTION_START.search(s):
        return True
    return False


def should_enable_ai_summary(prep: PreprocessedQuery) -> bool:
    """Gate auto AI summary: question/explanatory phrasing only; never nav or shopping intent."""
    if prep.intent in ("navigational", "transactional"):
        return False
    return has_informational_summary_signals(prep.original) or has_informational_summary_signals(
        prep.normalized
    )


_TRANSACTIONAL_LOCAL_UI = re.compile(
    r"\b("
    r"near|closest|nearest|nearby|around\s+here|in\s+my\s+area|open\s+now|"
    r"buy|order|shop\s+for|cheap(est)?|deal|delivery|pickup"
    r")\b",
    re.I,
)


def has_local_intent_signals(prep: PreprocessedQuery) -> bool:
    if prep.intent == "local_search":
        return True
    if prep.pattern and prep.pattern.kind in ("closest", "near_me", "near_poi", "best_in"):
        return True
    return False


def query_ui_hints(prep: PreprocessedQuery) -> Dict[str, Any]:
    """Signals for template/JS: interrogative vs transactional/local, AI summary, local chrome."""
    info_sig = has_informational_summary_signals(prep.original) or has_informational_summary_signals(
        prep.normalized
    )
    local_sig = has_local_intent_signals(prep)
    transactional_local = bool(_TRANSACTIONAL_LOCAL_UI.search(prep.normalized))
    return {
        "intent": prep.intent,
        "interrogative_or_explanatory": bool(info_sig),
        "local_intent": bool(local_sig),
        "transactional_local_keywords": transactional_local,
        "prefer_local_ui": bool(local_sig or transactional_local),
        "show_ai_summary": should_enable_ai_summary(prep),
    }


def resolve_location_for_search(
    prep: PreprocessedQuery,
    user_lat: Optional[float],
    user_lon: Optional[float],
    anchor_from_geocode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve place context: GPS, explicit place in query, or free-text near_me/closest.
    anchor_from_geocode: city/area label from reverse geocode when lat/lon are available.
    """
    has_local = has_local_intent_signals(prep)
    loc_from_query: Optional[str] = None
    if prep.pattern:
        if prep.pattern.kind in ("near_poi", "best_in") and prep.pattern.location:
            loc_from_query = prep.pattern.location.strip()
    return {
        "has_local_intent": bool(has_local),
        "user_lat": user_lat,
        "user_lon": user_lon,
        "location_from_query": loc_from_query,
        "anchor_label": (anchor_from_geocode or loc_from_query or "").strip() or None,
    }


def build_backend_search_query(
    clean_query: str,
    prep: PreprocessedQuery,
    loc: Dict[str, Any],
) -> str:
    """
    Rewrite into engine-friendly text (synonyms already in prep.normalized).
    Example: closest op shop → thrift store near me sorted by distance.
    """
    pat = prep.pattern
    q = ""

    if pat:
        if pat.kind == "closest" and pat.subject:
            subj = pat.subject.strip()
            q = f"{subj} near me sorted by distance"
        elif pat.kind == "near_me" and pat.subject:
            q = f"{pat.subject.strip()} near me open now"
        elif pat.kind == "near_poi" and pat.subject and pat.location:
            q = f"{pat.subject.strip()} near {pat.location.strip()}"
        elif pat.kind == "best_in" and pat.subject and pat.location:
            q = f"best {pat.subject.strip()} in {pat.location.strip()}"

    if not q:
        q = (prep.normalized or clean_query or "").strip()

    if loc.get("has_local_intent") and loc.get("user_lat") is not None and loc.get("user_lon") is not None:
        al = loc.get("anchor_label")
        if al and al.lower() not in q.lower():
            q = f"{q} near {al}".strip()
        elif not al:
            lat, lon = loc["user_lat"], loc["user_lon"]
            coord = f"{lat:.4f},{lon:.4f}"
            if coord not in q.replace(" ", ""):
                q = f"{q} near {coord}".strip()

    return q or (clean_query or "").strip()
