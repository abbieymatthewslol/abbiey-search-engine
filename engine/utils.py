from __future__ import annotations

import hashlib
import html
import logging
import re
from typing import Iterable
from urllib.parse import urlparse


logger = logging.getLogger("zero_click")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return normalize_whitespace(html.unescape(text))


def extract_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def stable_hash(parts: Iterable[str]) -> str:
    blob = "|".join(part or "" for part in parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def trusted_domain_score(domain: str) -> float:
    roots = {
        "wikipedia.org": 0.95,
        "en.wikipedia.org": 0.95,
        "britannica.com": 0.92,
        "open-meteo.com": 0.97,
        "github.com": 0.86,
        "developer.mozilla.org": 0.94,
        "docs.python.org": 0.97,
        "python.org": 0.97,
        "who.int": 0.98,
        "cdc.gov": 0.98,
        "nih.gov": 0.98,
        "nasa.gov": 0.98,
        "noaa.gov": 0.98,
        "reuters.com": 0.90,
        "apnews.com": 0.90,
        "bbc.com": 0.88,
        "bbc.co.uk": 0.88,
        "gov.au": 0.97,
        "vic.gov.au": 0.97,
        "australia.gov.au": 0.97,
    }

    for root, score in roots.items():
        if domain == root or domain.endswith("." + root):
            return score

    if domain.endswith(".gov") or domain.endswith(".gov.au"):
        return 0.95
    if domain.endswith(".edu") or domain.endswith(".edu.au"):
        return 0.90
    if domain.endswith(".org"):
        return 0.72
    return 0.55
