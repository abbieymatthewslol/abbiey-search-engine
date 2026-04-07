from __future__ import annotations

import re
from typing import List, Optional, Protocol

import httpx

from engine.calculator import SafeMathError, evaluate_expression, format_number, looks_like_math
from engine.models import AnswerContext, AnswerScore, SearchResult, SourceRef, ZeroClickAnswer
from engine.providers.wikipedia_provider import WikipediaProvider
from engine.utils import clamp01, extract_domain, normalize_whitespace, strip_html, trusted_domain_score


class AnswerHandler(Protocol):
    name: str
    priority: int

    def can_handle(self, ctx: AnswerContext) -> bool:
        ...

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        ...


class CalculatorHandler:
    name = "calculator"
    priority = 10

    def can_handle(self, ctx: AnswerContext) -> bool:
        return looks_like_math(ctx.query)

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        try:
            value = evaluate_expression(ctx.query)
        except SafeMathError:
            return None

        score = AnswerScore(
            parser_confidence=1.0,
            source_confidence=1.0,
            agreement_confidence=1.0,
            freshness_confidence=1.0,
        )
        return ZeroClickAnswer(
            answer_type="calculator",
            title="Calculator",
            summary=format_number(value),
            score=score,
            facts=[f"Expression: {ctx.query}"],
            confidence_explanation="Deterministic AST-based math evaluation.",
        )


class WeatherHandler:
    name = "weather"
    priority = 20

    def can_handle(self, ctx: AnswerContext) -> bool:
        return "weather" in ctx.query.lower() and ctx.weather is not None

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        weather = ctx.weather
        if weather is None:
            return None

        parts: List[str] = []
        if weather.current.temperature_c is not None:
            parts.append(f"{weather.current.temperature_c}�C")
        if weather.current.windspeed_kmh is not None:
            parts.append(f"wind {weather.current.windspeed_kmh} km/h")
        if weather.current.weather_code is not None:
            parts.append(f"code {weather.current.weather_code}")

        summary = f"{weather.location}: " + ", ".join(parts) if parts else weather.summary or weather.location
        score = AnswerScore(
            parser_confidence=0.98,
            source_confidence=0.98,
            agreement_confidence=0.95,
            freshness_confidence=1.0,
        )
        return ZeroClickAnswer(
            answer_type="weather",
            title=f"Weather � {weather.location}",
            summary=summary,
            score=score,
            facts=[weather.summary] if weather.summary else [],
            sources=[SourceRef(label="Open-Meteo", url="https://open-meteo.com/")],
            confidence_explanation="Structured weather payload from a trusted provider.",
        )


class EmailHandler:
    name = "email"
    priority = 30
    _pattern = re.compile(r"^([A-Z0-9._%+\-]+)@([A-Z0-9.\-]+\.[A-Z]{2,})$", re.I)

    def can_handle(self, ctx: AnswerContext) -> bool:
        return self._pattern.fullmatch(ctx.query) is not None

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        match = self._pattern.fullmatch(ctx.query)
        if match is None:
            return None

        local, domain = match.groups()
        is_plus = "+" in local
        is_role = local.lower() in {"admin", "support", "sales", "billing", "help", "contact", "info"}
        facts = [
            f"Local part: {local}",
            f"Domain: {domain.lower()}",
            f"Plus alias: {'yes' if is_plus else 'no'}",
            f"Role account pattern: {'yes' if is_role else 'no'}",
        ]
        score = AnswerScore(
            parser_confidence=0.99,
            source_confidence=1.0,
            agreement_confidence=1.0,
            freshness_confidence=1.0,
        )
        return ZeroClickAnswer(
            answer_type="email",
            title="Email Analysis",
            summary=f"{ctx.query} looks syntactically valid.",
            score=score,
            facts=facts,
            confidence_explanation="Deterministic syntax analysis.",
        )

class PhoneHandler:
    name = "phone"
    priority = 95  # LOW priority (runs last)

    def can_handle(self, ctx):
        q = ctx.query.strip()

        # HARD BLOCK non-phone patterns
        if "." in q or "," in q:
            return False

        # reject IP-like patterns
        if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", q):
            return False

        # reject coordinates
        if re.fullmatch(r"-?\d+\.\d+,\s*-?\d+\.\d+", q):
            return False

        cleaned = re.sub(r"[^\d+]", "", q)
        digits = re.sub(r"\D", "", cleaned)

        # strict requirement
        if not cleaned.startswith("+"):
            return False

        if not (8 <= len(digits) <= 15):
            return False

        return bool(re.fullmatch(r"\+?[0-9]{8,15}", cleaned))

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        cleaned = re.sub(r"[^\d+]", "", ctx.query)
        country = "Unknown"
        if cleaned.startswith("+61"):
            country = "Australia"
        elif cleaned.startswith("+1"):
            country = "United States / Canada"
        elif cleaned.startswith("+44"):
            country = "United Kingdom"

        score = AnswerScore(
            parser_confidence=0.90,
            source_confidence=1.0,
            agreement_confidence=1.0,
            freshness_confidence=1.0,
        )
        return ZeroClickAnswer(
            answer_type="phone",
            title="Phone Number Analysis",
            summary=f"{cleaned} matches a likely phone number format.",
            score=score,
            facts=[f"Normalized: {cleaned}", f"Likely region: {country}"],
            warnings=["Format validation is not the same as number ownership or live status."],
            confidence_explanation="Format-based phone heuristic.",
        )


class DomainHandler:
    name = "domain"
    priority = 50
    _pattern = re.compile(r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)

    def can_handle(self, ctx: AnswerContext) -> bool:
        return self._pattern.fullmatch(ctx.query.strip()) is not None

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        domain = ctx.query.strip().lower()
        labels = domain.split(".")
        tld = labels[-1]
        registrable = ".".join(labels[-2:]) if len(labels) >= 2 else domain
        score = AnswerScore(
            parser_confidence=0.96,
            source_confidence=1.0,
            agreement_confidence=1.0,
            freshness_confidence=1.0,
        )
        return ZeroClickAnswer(
            answer_type="domain",
            title="Domain Analysis",
            summary=f"{domain} looks like a valid domain.",
            score=score,
            facts=[
                f"TLD: .{tld}",
                f"Registrable domain: {registrable}",
                f"Subdomain count: {max(0, len(labels) - 2)}",
            ],
            confidence_explanation="Deterministic domain-pattern validation.",
        )


class IPv4Handler:
    name = "ipv4"
    priority = 60
    _pattern = re.compile(r"^((25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(25[0-5]|2[0-4]\d|1?\d?\d)$")

    def can_handle(self, ctx: AnswerContext) -> bool:
        return self._pattern.fullmatch(ctx.query.strip()) is not None

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        octets = [int(part) for part in ctx.query.split(".")]
        private = (
            octets[0] == 10
            or (octets[0] == 172 and 16 <= octets[1] <= 31)
            or (octets[0] == 192 and octets[1] == 168)
        )
        loopback = octets[0] == 127
        score = AnswerScore(
            parser_confidence=0.99,
            source_confidence=1.0,
            agreement_confidence=1.0,
            freshness_confidence=1.0,
        )
        return ZeroClickAnswer(
            answer_type="ip",
            title="IP Address Analysis",
            summary=f"{ctx.query} is a valid IPv4 address.",
            score=score,
            facts=[
                f"Private range: {'yes' if private else 'no'}",
                f"Loopback: {'yes' if loopback else 'no'}",
                f"Octets: {octets}",
            ],
            confidence_explanation="Deterministic IPv4 validation.",
        )


class CoordinatesHandler:
    name = "coordinates"
    priority = 70
    _pattern = re.compile(r"^\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")

    def can_handle(self, ctx: AnswerContext) -> bool:
        return self._pattern.fullmatch(ctx.query) is not None

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        match = self._pattern.fullmatch(ctx.query)
        if match is None:
            return None

        lat = float(match.group(1))
        lon = float(match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None

        ns = "N" if lat >= 0 else "S"
        ew = "E" if lon >= 0 else "W"
        score = AnswerScore(
            parser_confidence=0.98,
            source_confidence=1.0,
            agreement_confidence=1.0,
            freshness_confidence=1.0,
        )
        return ZeroClickAnswer(
            answer_type="coordinates",
            title="Coordinates",
            summary=f"{abs(lat):.6f}� {ns}, {abs(lon):.6f}� {ew}",
            score=score,
            facts=[f"Latitude: {lat}", f"Longitude: {lon}"],
            confidence_explanation="Deterministic coordinate validation.",
        )


class CryptoAddressHandler:
    name = "crypto_address"
    priority = 80
    _patterns = [
        ("bitcoin", re.compile(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,90}$")),
        ("ethereum", re.compile(r"^0x[a-fA-F0-9]{40}$")),
        ("solana", re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")),
    ]

    def can_handle(self, ctx: AnswerContext) -> bool:
        value = ctx.query.strip()
        return any(pattern.fullmatch(value) for _, pattern in self._patterns)

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        value = ctx.query.strip()
        for network, pattern in self._patterns:
            if pattern.fullmatch(value):
                score = AnswerScore(
                    parser_confidence=0.93,
                    source_confidence=1.0,
                    agreement_confidence=1.0,
                    freshness_confidence=1.0,
                )
                return ZeroClickAnswer(
                    answer_type="crypto_address",
                    title="Crypto Address Analysis",
                    summary=f"This looks like a {network.capitalize()} address.",
                    score=score,
                    facts=[f"Detected network: {network}", f"Length: {len(value)}"],
                    warnings=["Pattern match only. It does not prove chain activity or ownership."],
                    confidence_explanation="Format-based crypto-address detection.",
                )
        return None


class WikipediaEntityHandler:
    name = "wikipedia_entity"
    priority = 90

    def __init__(self, provider: WikipediaProvider) -> None:
        self.provider = provider

    def can_handle(self, ctx: AnswerContext) -> bool:
        q = ctx.query.strip()
        if len(q) < 3:
            return False
        if re.search(r"[@:/]", q):
            return False
        if re.search(r"\b(weather|http|www\.|@\w+)\b", q.lower()):
            return False
        return True

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        try:
            result = self.provider.lookup_summary(ctx.query)
        except httpx.TimeoutException:
            return None
        except httpx.HTTPError:
            return None

        if result is None:
            return None

        parser_conf = 0.90
        if result.title.lower() == ctx.query.strip().lower():
            parser_conf = 0.95

        score = AnswerScore(
            parser_confidence=parser_conf,
            source_confidence=0.95,
            agreement_confidence=0.85,
            freshness_confidence=0.60,
        )
        return ZeroClickAnswer(
            answer_type="entity_summary",
            title=result.title,
            summary=result.summary,
            score=score,
            facts=[result.description] if result.description else [],
            sources=[SourceRef(label="Wikipedia", url=result.page_url)],
            warnings=["Entity summaries may be incomplete or stale for fast-changing topics."],
            confidence_explanation="Single-source entity summary from Wikipedia.",
        )


class SearchConsensusHandler:
    name = "search_consensus"
    priority = 100

    def can_handle(self, ctx: AnswerContext) -> bool:
        return len(ctx.search_results) >= 2

    def handle(self, ctx: AnswerContext) -> Optional[ZeroClickAnswer]:
        cleaned = self._clean_results(ctx.search_results[:8])
        if len(cleaned) < 2:
            return None

        candidates: dict[str, dict] = {}
        for item in cleaned:
            sentences = re.split(r"(?<=[.!?])\s+", item["snippet"])
            for sentence in sentences[:3]:
                sentence = normalize_whitespace(sentence)
                if len(sentence) < 35 or len(sentence) > 220:
                    continue
                key = re.sub(r"[^a-z0-9 ]+", "", sentence.lower())
                key = normalize_whitespace(key)
                if len(key.split()) < 6:
                    continue

                bucket = candidates.setdefault(
                    key,
                    {
                        "sentence": sentence,
                        "support": 0.0,
                        "sources": [],
                        "domains": set(),
                    },
                )
                bucket["support"] += item["trust"]
                bucket["sources"].append(SourceRef(label=item["domain"] or "source", url=item["url"]))
                bucket["domains"].add(item["domain"])

        if not candidates:
            return None

        best = sorted(candidates.values(), key=lambda x: x["support"], reverse=True)[0]
        domain_count = len(best["domains"])
        if domain_count < 2:
            return None

        parser_confidence = clamp01(0.65 + (domain_count * 0.08))
        source_confidence = clamp01(best["support"] / max(2.0, len(cleaned)))
        agreement_confidence = clamp01(min(1.0, domain_count / 4.0))
        score = AnswerScore(
            parser_confidence=parser_confidence,
            source_confidence=source_confidence,
            agreement_confidence=agreement_confidence,
            freshness_confidence=0.50,
        )

        if score.total < 0.82:
            return None

        return ZeroClickAnswer(
            answer_type="search_consensus",
            title="Direct Answer",
            summary=best["sentence"],
            score=score,
            facts=[f"Consensus across {domain_count} source domains"],
            sources=best["sources"][:4],
            warnings=["Snippet consensus can still be wrong for disputed or breaking topics."],
            confidence_explanation="Consensus derived from multiple result snippets and domain trust.",
        )

    def _clean_results(self, items: List[SearchResult]) -> List[dict]:
        cleaned: List[dict] = []
        for item in items:
            title = normalize_whitespace(item.title)
            snippet = strip_html(item.snippet)
            url = item.url
            domain = extract_domain(url)
            if not title and not snippet:
                continue
            cleaned.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "url": url,
                    "domain": domain,
                    "trust": trusted_domain_score(domain),
                }
            )
        return cleaned


