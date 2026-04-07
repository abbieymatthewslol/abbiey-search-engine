from __future__ import annotations

import logging
from typing import Iterable, Optional

from engine.cache import TTLCacheLite
from engine.handlers import (
    CalculatorHandler,
    CoordinatesHandler,
    CryptoAddressHandler,
    DomainHandler,
    EmailHandler,
    IPv4Handler,
    PhoneHandler,
    SearchConsensusHandler,
    WeatherHandler,
    WikipediaEntityHandler,
)
from engine.models import AnswerContext, SearchResult, WeatherCurrent, WeatherPayload, ZeroClickAnswer
from engine.providers.wikipedia_provider import WikipediaProvider
from engine.utils import stable_hash


logger = logging.getLogger("zero_click")


class ZeroClickEngine:
    def __init__(
        self,
        cache_ttl_seconds: int = 600,
        cache_maxsize: int = 512,
        wikipedia_provider: Optional[WikipediaProvider] = None,
    ) -> None:
        self.cache = TTLCacheLite(maxsize=cache_maxsize, ttl_seconds=cache_ttl_seconds)
        provider = wikipedia_provider or WikipediaProvider()
        self.handlers = sorted(
            [
                CalculatorHandler(),
                WeatherHandler(),
                EmailHandler(),
                PhoneHandler(),
                DomainHandler(),
                IPv4Handler(),
                CoordinatesHandler(),
                CryptoAddressHandler(),
                WikipediaEntityHandler(provider),
                SearchConsensusHandler(),
            ],
            key=lambda h: h.priority,
        )

    def answer(
        self,
        query: str,
        search_results: Optional[Iterable[dict | SearchResult]] = None,
        weather_payload: Optional[dict | WeatherPayload] = None,
        locale: str = "en-AU",
        region: str = "AU",
    ) -> Optional[ZeroClickAnswer]:
        ctx = AnswerContext(
            query=query.strip(),
            search_results=self._normalize_results(search_results or []),
            weather=self._normalize_weather(weather_payload),
            locale=locale,
            region=region,
        )
        if not ctx.query:
            return None

        cache_key = self._build_cache_key(ctx)
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug("zero_click cache hit query=%r", ctx.query)
            return cached

        logger.debug("zero_click evaluating query=%r", ctx.query)

        for handler in self.handlers:
            if not handler.can_handle(ctx):
                continue

            logger.debug("zero_click trying handler=%s query=%r", handler.name, ctx.query)
            answer = handler.handle(ctx)
            if answer is None:
                continue

            logger.debug(
                "zero_click selected handler=%s confidence=%.3f query=%r",
                handler.name,
                answer.confidence,
                ctx.query,
            )
            self.cache.set(cache_key, answer)
            return answer

        logger.debug("zero_click no_answer query=%r", ctx.query)
        return None

    def should_show(self, answer: Optional[ZeroClickAnswer], threshold: float = 0.82) -> bool:
        if answer is None:
            return False
        return answer.confidence >= threshold

    def _build_cache_key(self, ctx: AnswerContext) -> str:
        weather_marker = ""
        if ctx.weather is not None:
            weather_marker = f"{ctx.weather.location}|{ctx.weather.summary}|{ctx.weather.current.temperature_c}|{ctx.weather.current.windspeed_kmh}|{ctx.weather.current.weather_code}"

        result_marker = "|".join(f"{r.title}|{r.url}" for r in ctx.search_results[:5])
        return stable_hash([ctx.query, ctx.locale, ctx.region, weather_marker, result_marker])

    def _normalize_results(self, items: Iterable[dict | SearchResult]) -> list[SearchResult]:
        normalized: list[SearchResult] = []
        for item in items:
            if isinstance(item, SearchResult):
                normalized.append(item)
                continue

            normalized.append(
                SearchResult(
                    title=str(item.get("title") or ""),
                    snippet=str(item.get("snippet") or item.get("body") or ""),
                    url=str(item.get("url") or item.get("href") or ""),
                )
            )
        return normalized

    def _normalize_weather(self, payload: Optional[dict | WeatherPayload]) -> Optional[WeatherPayload]:
        if payload is None:
            return None
        if isinstance(payload, WeatherPayload):
            return payload

        current = payload.get("current") or {}
        return WeatherPayload(
            location=str(payload.get("location") or "Unknown location"),
            summary=str(payload.get("summary") or ""),
            current=WeatherCurrent(
                temperature_c=_to_float_or_none(current.get("temperature") if "temperature" in current else current.get("temperature_c")),
                windspeed_kmh=_to_float_or_none(current.get("windspeed") if "windspeed" in current else current.get("windspeed_kmh")),
                weather_code=_to_int_or_none(current.get("weather_code")),
            ),
        )


def _to_float_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
