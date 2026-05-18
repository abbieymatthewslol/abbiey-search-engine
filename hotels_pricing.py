"""Hotel price scraping — HTML search + nightly-rate extraction.

Fetches human-readable DuckDuckGo HTML results (server-friendly POST), parses
titles/snippets for money amounts, and merges with ddgs JSON results. Ad
``y.js`` URLs are expanded using the caller's booking deep-links when possible.

Prices are *indicative*: they come from result titles/snippets (OTAs, blogs,
aggregators) and are sorted so the lowest parsed nightly estimate appears first.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

logger = logging.getLogger(__name__)

_DDG_HTML = "https://html.duckduckgo.com/html/"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HTTP_TIMEOUT = httpx.Timeout(14.0, connect=6.0)
_MAX_DDGS = 8
_MAX_HTML_QUERIES = 2
_MAX_ROWS_TOTAL = 18

# Approximate FX to USD for sorting only (not for billing).
_TO_USD = {
    "USD": Decimal("1"),
    "EUR": Decimal("1.08"),
    "GBP": Decimal("1.27"),
    "AUD": Decimal("0.64"),
    "CAD": Decimal("0.71"),
    "NZD": Decimal("0.59"),
    "JPY": Decimal("0.0067"),
}

_MONEY_BLOCK = r"(?:USD|US\s*\$|AUD|A\$|CAD|C\$|NZD|N\$|EUR|€|GBP|£|JPY|¥)"

# Order matters: more specific patterns first.
_PRICE_RES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(?:from|under|up\s+to|only|just|average|from)\s*" + _MONEY_BLOCK + r"\s*([\d,]+)"), "CTX"),
    (re.compile(r"(?i)" + _MONEY_BLOCK + r"\s*([\d,]+)\s*(?:/night|per\s+night|pn\b|a\s+night)"), "NIGHT"),
    (re.compile(r"(?i)(?:US\s*\$|\$)\s*([\d,]+)\s*(?:/night|per\s+night)?"), "DOLLAR"),
    (re.compile(r"(?i)€\s*([\d,]+)"), "EUR"),
    (re.compile(r"(?i)£\s*([\d,]+)"), "GBP"),
    (re.compile(r"(?i)¥\s*([\d,]+)"), "JPY"),
    (re.compile(r"(?i)(?:AUD|A\$)\s*([\d,]+)"), "AUD"),
    (re.compile(r"(?i)(?:CAD|C\$)\s*([\d,]+)"), "CAD"),
    (re.compile(r"(?i)(?:NZD|N\$)\s*([\d,]+)"), "NZD"),
]


def _parse_amount(raw: str) -> Decimal | None:
    s = raw.replace(",", "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _infer_currency_from_label(label: str, text_lower: str, host: str) -> str:
    u = label.upper()
    if "EUR" in u or label == "EUR":
        return "EUR"
    if "GBP" in u or label == "GBP":
        return "GBP"
    if "JPY" in u or label == "JPY":
        return "JPY"
    if "AUD" in u or "A$" in label or ".au" in host or "australia" in text_lower:
        return "AUD"
    if "CAD" in u or "C$" in label or host.endswith(".ca"):
        return "CAD"
    if "NZD" in u or "N$" in label or host.endswith(".nz") or "new zealand" in text_lower:
        return "NZD"
    if "USD" in u or "US$" in label:
        return "USD"
    if label == "DOLLAR":
        if ".com.au" in host or ".co.nz" in host or "skyscanner.com.au" in host:
            return "AUD"
        return "USD"
    if label == "NIGHT" and "€" in text_lower and "$" not in text_lower:
        return "EUR"
    if label == "NIGHT":
        if ".com.au" in host or "booking.com" in host and "australia" in text_lower:
            return "AUD"
        return "USD"
    if label == "CTX":
        if "€" in text_lower:
            return "EUR"
        if "£" in text_lower:
            return "GBP"
        if ".com.au" in host or "aud" in text_lower:
            return "AUD"
        return "USD"
    return "USD"


def _min_nightly_price_usd(title: str, snippet: str, host: str) -> tuple[Decimal | None, str | None]:
    blob = f"{title}\n{snippet}"
    lower = blob.lower()
    best_amt: Decimal | None = None
    best_cur: str | None = None
    for rx, label in _PRICE_RES:
        for m in rx.finditer(blob):
            groups = m.groups()
            if not groups:
                continue
            amt = _parse_amount(groups[-1])
            if amt is None or amt <= 0:
                continue
            if label == "JPY" and amt < 300:
                continue
            cur = _infer_currency_from_label(label, lower, host)
            adj = amt * _TO_USD.get(cur, Decimal("1"))
            if best_amt is None or adj < best_amt:
                best_amt = adj
                sym = {"$": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "AUD": "A$", "CAD": "C$", "NZD": "NZ$"}.get(
                    cur, "$"
                )
                if cur == "JPY":
                    best_cur = f"{sym}{int(amt)}"
                else:
                    best_cur = f"{sym}{amt:.0f}" if amt == amt.to_integral() else f"{sym}{amt:.2f}"
    if best_amt is not None and best_cur:
        equiv = f"~US${best_amt:.0f}" if best_amt == best_amt.to_integral() else f"~US${best_amt:.2f}"
        return best_amt, f"{best_cur} nightly ({equiv})"
    return None, None


def _urls_by_host(booking_links: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in booking_links:
        u = (row.get("url") or "").strip()
        if not u:
            continue
        host = urlparse(u).netloc.lower().replace("www.", "")
        out[host] = u
    return out


def _expand_ddg_url(href: str, host_map: dict[str, str]) -> str:
    if not href:
        return href
    p = urlparse(href)
    if "duckduckgo.com" not in (p.netloc or "").lower():
        return href
    if not (p.path or "").rstrip("/").endswith("y.js"):
        return href
    qs = parse_qs(p.query)
    dom_list = qs.get("ad_domain") or []
    if not dom_list:
        return href
    ad = (dom_list[0] or "").strip().lower().replace("www.", "")
    if not ad:
        return href
    for h, booking_link in host_map.items():
        if h == ad or h.endswith("." + ad) or ad.endswith("." + h.split(".")[-1]):
            return booking_link
    return f"https://www.{ad}/"


def _fetch_ddg_html(client: httpx.Client, query: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        r = client.post(
            _DDG_HTML,
            data={"q": query, "b": ""},
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://duckduckgo.com/",
            },
        )
        r.raise_for_status()
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("hotels_ddg_html_failed q=%s err=%s", query[:80], exc)
        return rows

    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.select("a.result__a"):
        title = a.get_text(" ", strip=True)
        href = (a.get("href") or "").strip()
        if not title or not href:
            continue
        body = a.find_parent("div", class_=lambda c: c and "result__body" in c)
        sn_el = body.select_one(".result__snippet") if body else None
        snippet = sn_el.get_text(" ", strip=True) if sn_el else ""
        rows.append({"title": title, "url": href, "snippet": snippet, "source": "duckduckgo-html"})
    return rows


def _ddgs_fallback(destination: str, checkin: str, checkout: str, guests: int) -> list[dict[str, str]]:
    date_hint = ""
    if checkin and checkout:
        date_hint = f" {checkin} to {checkout}"
    elif checkin:
        date_hint = f" from {checkin}"
    query = f"hotels in {destination}{date_hint} {guests} guests book"
    try:
        out: list[dict[str, str]] = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=_MAX_DDGS):
                href = r.get("href", r.get("url", ""))
                out.append(
                    {
                        "title": r.get("title", ""),
                        "url": href,
                        "snippet": r.get("body", r.get("description", "")),
                        "source": "ddgs-api",
                    }
                )
        return out
    except Exception:
        logger.exception("hotels_ddgs_fallback_failed destination=%s", destination)
        return []


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def search_hotels_with_prices(
    destination: str,
    checkin: str,
    checkout: str,
    guests: int,
    booking_links: list[dict],
) -> tuple[list[dict], dict]:
    """Return sorted hotel rows (cheapest parsed nightly first) and meta dict."""
    dest_q = destination.strip()
    if not dest_q:
        return [], {}

    host_map = _urls_by_host(booking_links)
    q_dates = ""
    if checkin and checkout:
        q_dates = f"{checkin} {checkout}"
    elif checkin:
        q_dates = checkin

    queries = [
        f"cheapest hotels {dest_q} per night price book {q_dates}".strip(),
        f"{dest_q} hotel deals compare prices nightly {guests} guests {q_dates}".strip(),
    ][: _MAX_HTML_QUERIES]

    raw_rows: list[dict[str, str]] = []
    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": _USER_AGENT}) as client:
        for q in queries:
            raw_rows.extend(_fetch_ddg_html(client, q))
    raw_rows.extend(_ddgs_fallback(dest_q, checkin, checkout, guests))

    seen: set[str] = set()
    merged: list[dict] = []
    for row in raw_rows:
        url0 = (row.get("url") or "").strip()
        exp = _expand_ddg_url(url0, host_map)
        host = _domain_from_url(exp)
        tkey = re.sub(r"\s+", " ", (row.get("title") or "").lower()).strip()[:200]
        if not tkey:
            tkey = (row.get("snippet") or "")[:120].lower()
        if not tkey or tkey in seen:
            continue
        seen.add(tkey)
        pu, pdisp = _min_nightly_price_usd(row.get("title", ""), row.get("snippet", ""), host)
        merged.append(
            {
                "title": row.get("title", ""),
                "url": exp,
                "snippet": row.get("snippet", ""),
                "source": host or row.get("source", ""),
                "scrape_source": row.get("source", ""),
                "price_usd": float(pu) if pu is not None else None,
                "price_display": pdisp,
            }
        )
        if len(merged) >= _MAX_ROWS_TOTAL:
            break

    priced = [r for r in merged if r.get("price_usd") is not None]
    unpriced = [r for r in merged if r.get("price_usd") is None]
    priced.sort(key=lambda r: (r["price_usd"], r["title"]))
    results = priced + unpriced

    cheapest = results[0] if results else None
    meta = {
        "cheapest": cheapest,
        "disclaimer": (
            "Nightly prices are parsed from live search snippets (not direct OTA checkout). "
            "Totals, taxes, and room type may differ—confirm on the booking site."
        ),
    }
    return results, meta
