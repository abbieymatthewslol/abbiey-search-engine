"""URL path helpers for /search/<type> canonical routes."""

from __future__ import annotations

from typing import FrozenSet, Optional, Tuple
from urllib.parse import urlencode


def normalize_type_arg(raw: str, allowed: FrozenSet[str]) -> str:
    t = (raw or "text").strip().lower()
    if t not in allowed:
        return "text"
    return t


def resolve_search_type_path(
    path_stype: Optional[str],
    args_type_raw: str,
    allowed: FrozenSet[str],
) -> Tuple[str, Optional[str]]:
    """Resolve search tab type from Flask path segment and ``?type=``.

    Path wins when valid. Unknown path segments return *(fallback_from_query_type, sentinel)*
    so the caller can 301 redirect to ``/search?`` with the query string unchanged.
    """
    args_norm = normalize_type_arg(args_type_raw, allowed)
    if path_stype is None:
        return args_norm, None
    seg = path_stype.strip().lower()
    if seg not in allowed:
        return args_norm, "invalid-path"
    return seg, None


def search_mode_href(
    tab: str,
    q: str,
    *,
    region: str = "",
    lang: str = "",
    time_filter: str = "",
    safesearch: str = "",
    cleanweb: bool = False,
    open_knowledge: bool = False,
    onion_mode: str = "",
    img_scroll_extras: str = "",
    people_pf_extra: str = "",
    mybot_id=None,
    search_type_saved: bool = False,
) -> str:
    """Relative URL for switching search tabs (/search or /search/<mode>?q=&…)."""
    t = (tab or "text").strip().lower()
    if t == "saved" or search_type_saved:
        t = "saved"
    path = "/search" if t in ("text", "") else f"/search/{t}"
    pairs = []
    qs_val = q or ""
    if tab == "saved" or qs_val or t == "saved":
        pairs.append(("q", qs_val))
    if region:
        pairs.append(("region", region))
    if lang:
        pairs.append(("lang", lang))
    if time_filter:
        pairs.append(("df", time_filter))
    if safesearch and safesearch != "off":
        pairs.append(("safesearch", safesearch))
    if cleanweb:
        pairs.append(("cleanweb", "1"))
    if open_knowledge:
        pairs.append(("open_knowledge", "1"))
    if onion_mode:
        pairs.append(("onion_mode", onion_mode))
    if mybot_id is not None:
        try:
            pairs.append(("bot_id", str(int(mybot_id))))
        except (TypeError, ValueError):
            pass
    stem = urlencode(pairs)
    extras = []
    if img_scroll_extras:
        frag = img_scroll_extras.strip().lstrip("&")
        if frag:
            extras.append(frag)
    if people_pf_extra:
        p = people_pf_extra.strip()
        if p.startswith("&"):
            p = p.lstrip("&")
        if p:
            extras.append(p)
    tail = "&".join([stem] + extras) if extras else stem
    return path + ("?" + tail if tail else "")


def search_mode_title_suffix(search_type: str) -> str:
    """Human label for `<title>` on result pages."""
    m = {
        "text": "Web search",
        "images": "Image search",
        "news": "News search",
        "videos": "Video search",
        "code": "Code search",
        "people": "People OSINT search",
        "email": "Email search",
        "business": "Business search",
        "onion": ".onion index search",
        "saved": "Saved searches",
        "mybot": "Custom bot search",
        "prices": "Price search",
        "alts": "Alternatives search",
    }
    return m.get((search_type or "text").strip().lower(), "Search")
