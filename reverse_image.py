"""Reverse image lookup via Bing Images HTML (imgurl:…).

Used when a user pastes a direct HTTPS image URL, or when an upload is exposed
temporarily at ``/api/reverse-image/preview/<token>`` so Bing can fetch it once.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

BING_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"

# Bing embeds image rows as JSON-ish strings with purl (page), murl (image file), t (caption).
_PAIR_RE = re.compile(
    r'purl":"(https://[^"]+)","murl":"(https://[^"]+)"[\s\S]{0,240}?"t":"((?:[^"\\]|\\.)*)"',
)


def _title_from_caption(t: str) -> str:
    t = (t or "").strip()
    if not t:
        return "Image result"
    if t.lower().startswith("http") and "," in t:
        rest = t.split(",", 1)[1].strip()
        if rest:
            return rest[:220]
    return t[:220]


def parse_bing_reverse_html(page_html: str) -> list[dict]:
    """Extract similar-image rows from a Bing Images reverse-search HTML page."""
    chunk = html_lib.unescape(page_html or "")
    seen: set[str] = set()
    out: list[dict] = []
    for purl, murl, raw_t in _PAIR_RE.findall(chunk):
        if murl in seen:
            continue
        seen.add(murl)
        tit = raw_t.replace("\\u002f", "/").replace("\\u003a", ":")
        if "\\u" in tit:
            try:
                tit2 = tit.encode("utf-8", "surrogatepass").decode("unicode_escape")
                if tit2:
                    tit = tit2
            except Exception:
                pass
        title = _title_from_caption(tit)
        body = tit[:900] if tit else ""
        host = ""
        try:
            host = urlparse(purl).netloc or urlparse(murl).netloc
        except Exception:
            host = ""
        out.append(
            {
                "title": title,
                "url": purl,
                "image": murl,
                "thumbnail": murl,
                "source": host,
                "body": body,
            }
        )
        if len(out) >= 40:
            break
    return out


def fetch_reverse_hits_for_image_url(image_url: str, *, client: httpx.Client) -> list[dict]:
    """GET Bing Images reverse search for a publicly reachable image URL."""
    image_url = (image_url or "").strip()
    if not image_url.lower().startswith("https://"):
        return []
    try:
        r = client.get(
            "https://www.bing.com/images/search",
            params={"q": "imgurl:" + image_url},
            headers={"User-Agent": BING_UA, "Accept-Language": "en-US,en;q=0.9"},
            timeout=10.0,
            follow_redirects=True,
        )
        r.raise_for_status()
        return parse_bing_reverse_html(r.text)
    except Exception:
        logger.warning("bing_reverse_image_failed", exc_info=True)
        return []


def validate_client_image_url(url: str) -> tuple[bool, str]:
    """Only allow https image URLs suitable for server-side fetch + Bing relay."""
    u = (url or "").strip()
    if not u:
        return False, "empty"
    p = urlparse(u)
    if p.scheme != "https":
        return False, "https_only"
    if not p.netloc or "." not in p.netloc:
        return False, "bad_host"
    path = (p.path or "").lower()
    if path.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif")):
        return True, ""
    if "/image" in path or "format=jpg" in u.lower():
        return True, ""
    return True, ""
