from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import httpx

from engine.utils import normalize_whitespace


USER_AGENT = "abbieysearch-zero-click/2.0"


@dataclass(slots=True)
class WikipediaSummary:
    title: str
    summary: str
    description: str
    page_url: str


class WikipediaProvider:
    def __init__(self, timeout_seconds: float = 4.0) -> None:
        self.timeout_seconds = timeout_seconds

    def lookup_summary(self, query: str) -> Optional[WikipediaSummary]:
        q = normalize_whitespace(query)
        if len(q) < 3:
            return None

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            title = self._resolve_title(client, q)
            if not title:
                return None

            encoded = quote(title, safe="")
            response = client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}")
            response.raise_for_status()
            payload = response.json()

        summary = normalize_whitespace(payload.get("extract") or "")
        if len(summary) < 30:
            return None

        content_urls = ((payload.get("content_urls") or {}).get("desktop") or {})
        page_url = content_urls.get("page") or f"https://en.wikipedia.org/wiki/{encoded}"

        return WikipediaSummary(
            title=normalize_whitespace(payload.get("title") or title),
            summary=summary,
            description=normalize_whitespace(payload.get("description") or ""),
            page_url=page_url,
        )

    def _resolve_title(self, client: httpx.Client, query: str) -> Optional[str]:
        encoded = quote(query, safe="")
        response = client.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}")
        if response.status_code == 200:
            payload = response.json()
            title = normalize_whitespace(payload.get("title") or "")
            if title:
                return title

        search_response = client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
            },
        )
        search_response.raise_for_status()
        payload = search_response.json()
        hits = ((payload.get("query") or {}).get("search") or [])
        if not hits:
            return None
        return normalize_whitespace(hits[0].get("title") or "")
