from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


AnswerType = Literal[
    "calculator",
    "weather",
    "email",
    "phone",
    "domain",
    "ip",
    "coordinates",
    "crypto_address",
    "entity_summary",
    "search_consensus",
]


@dataclass(slots=True)
class SourceRef:
    label: str
    url: str


@dataclass(slots=True)
class SearchResult:
    title: str
    snippet: str
    url: str


@dataclass(slots=True)
class WeatherCurrent:
    temperature_c: Optional[float] = None
    windspeed_kmh: Optional[float] = None
    weather_code: Optional[int] = None


@dataclass(slots=True)
class WeatherPayload:
    location: str
    summary: str = ""
    current: WeatherCurrent = field(default_factory=WeatherCurrent)


@dataclass(slots=True)
class AnswerContext:
    query: str
    search_results: List[SearchResult] = field(default_factory=list)
    weather: Optional[WeatherPayload] = None
    locale: str = "en-AU"
    region: str = "AU"


@dataclass(slots=True)
class AnswerScore:
    parser_confidence: float = 0.0
    source_confidence: float = 0.0
    agreement_confidence: float = 0.0
    freshness_confidence: float = 0.5

    @property
    def total(self) -> float:
        value = (
            (self.parser_confidence * 0.40)
            + (self.source_confidence * 0.25)
            + (self.agreement_confidence * 0.25)
            + (self.freshness_confidence * 0.10)
        )
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value


@dataclass(slots=True)
class ZeroClickAnswer:
    answer_type: AnswerType
    title: str
    summary: str
    score: AnswerScore
    facts: List[str] = field(default_factory=list)
    sources: List[SourceRef] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence_explanation: str = ""

    @property
    def confidence(self) -> float:
        return self.score.total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer_type": self.answer_type,
            "title": self.title,
            "summary": self.summary,
            "confidence": round(self.confidence, 4),
            "facts": list(self.facts),
            "warnings": list(self.warnings),
            "confidence_explanation": self.confidence_explanation,
            "sources": [{"label": s.label, "url": s.url} for s in self.sources],
        }
