"""
OSINT orchestration: module whitelist, TTL cache, entity routing.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx
from cachetools import TTLCache

from entity_parser import Entity, detect_entities, primary_entity
from osint import kali_tools, modules

_CACHE: TTLCache = TTLCache(maxsize=400, ttl=300)
_CACHE_LOCK = __import__("threading").Lock()

_DISCLAIMER = (
    "Signals are derived from public DNS, RDAP, reverse-DNS, optional TLS metadata, "
    "and—when installed—local dig/whois output (typical on Kali/Linux dev systems). "
    "They may be incomplete or stale. Do not use this output for unlawful or harmful purposes."
)

_DEFAULT_MODULES = frozenset({"dns", "rdap", "ptr"})


def is_osint_enabled() -> bool:
    v = (os.environ.get("ABBIEY_OSINT_ENABLED") or "").strip().lower()
    if not v:
        return True
    return v not in ("0", "false", "no", "off")


def parse_enabled_modules() -> frozenset[str]:
    raw = (os.environ.get("ABBIEY_OSINT_MODULES") or "").strip().lower()
    if not raw:
        return _DEFAULT_MODULES
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    allowed = {"dns", "rdap", "ptr", "tls", "dig", "whois"}
    return frozenset(parts & allowed) or _DEFAULT_MODULES


def _cache_key(entity_type: str, value: str, mods: frozenset[str]) -> str:
    h = hashlib.sha256(
        f"{entity_type}|{value.lower()}|{','.join(sorted(mods))}".encode("utf-8", errors="replace")
    )
    return h.hexdigest()


def _normalize_email_domain(value: str) -> str | None:
    s = (value or "").strip().lower()
    if "@" not in s:
        return None
    dom = s.rsplit("@", 1)[-1]
    return modules._validate_domain(dom)


def enrich(
    *,
    entity_type: str,
    value: str,
    enabled_modules: frozenset[str] | None = None,
) -> dict[str, Any]:
    """
    Run whitelisted modules for domain | ip | email (mail domain only).

    Returns JSON-safe dict: facts, modules, entity, disclaimer.
    """
    mods = enabled_modules if enabled_modules is not None else parse_enabled_modules()
    et = (entity_type or "").strip().lower()
    val = (value or "").strip()
    if et not in ("domain", "ip", "email") or not val:
        return {
            "ok": False,
            "error": "invalid_entity",
            "facts": [],
            "modules": [],
            "entity": None,
            "disclaimer": _DISCLAIMER,
        }

    if et == "email":
        dom = _normalize_email_domain(val)
        if not dom:
            return {
                "ok": False,
                "error": "invalid_email",
                "facts": [],
                "modules": [],
                "entity": None,
                "disclaimer": _DISCLAIMER,
            }
        et = "domain"
        val = dom

    if et == "domain" and not modules._validate_domain(val):
        return {
            "ok": False,
            "error": "invalid_domain",
            "facts": [],
            "modules": [],
            "entity": None,
            "disclaimer": _DISCLAIMER,
        }
    if et == "ip" and not modules._validate_ipv4(val):
        return {
            "ok": False,
            "error": "invalid_ip",
            "facts": [],
            "modules": [],
            "entity": None,
            "disclaimer": _DISCLAIMER,
        }

    key = _cache_key(et, val, mods)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None:
        return hit

    used: list[str] = []
    facts: list[dict[str, Any]] = []

    with httpx.Client(follow_redirects=True) as client:
        if et == "domain":
            if "dns" in mods:
                facts.extend(modules.dns_facts(val, client))
                used.append("dns")
            if "rdap" in mods:
                facts.extend(modules.rdap_domain_facts(val, client))
                used.append("rdap")
            if "tls" in mods:
                tls_rows = modules.tls_cert_facts(val)
                if tls_rows:
                    facts.extend(tls_rows)
                    used.append("tls")
            if "dig" in mods:
                dig_rows = kali_tools.dig_facts(val)
                if dig_rows:
                    facts.extend(dig_rows)
                    used.append("dig")
            if "whois" in mods:
                whois_rows = kali_tools.whois_facts(val)
                if whois_rows:
                    facts.extend(whois_rows)
                    used.append("whois")
        elif et == "ip":
            if "ptr" in mods:
                facts.extend(modules.ptr_fact(val))
                used.append("ptr")
            if "rdap" in mods:
                facts.extend(modules.rdap_ip_facts(val, client))
                used.append("rdap")
            if "dig" in mods:
                dig_rev = kali_tools.dig_reverse_facts(val)
                if dig_rev:
                    facts.extend(dig_rev)
                    used.append("dig")

    out = {
        "ok": True,
        "error": None,
        "facts": facts,
        "modules": used,
        "entity": {"type": et, "value": val},
        "disclaimer": _DISCLAIMER,
    }
    with _CACHE_LOCK:
        _CACHE[key] = out
    return out


def enrich_from_query(query: str) -> dict[str, Any]:
    """Detect primary entity; only domain, ip, or email are supported."""
    q = (query or "").strip()
    if not q or len(q) > 8000:
        return {
            "ok": False,
            "error": "unsupported_or_empty",
            "facts": [],
            "modules": [],
            "entity": None,
            "disclaimer": _DISCLAIMER,
        }
    entities = detect_entities(q)
    prim: Entity | None = primary_entity(entities)
    if prim and prim.type in ("domain", "ip", "email"):
        return enrich(entity_type=prim.type, value=prim.normalized)
    # Single-token domain or IPv4 in query
    token = q.split()[0] if q else ""
    if token and modules._validate_domain(token):
        return enrich(entity_type="domain", value=token)
    if token and modules._validate_ipv4(token):
        return enrich(entity_type="ip", value=token)
    if _EMAIL_SINGLE.match(q.strip()):
        return enrich(entity_type="email", value=q.strip())
    return {
        "ok": False,
        "error": "unsupported_entity",
        "facts": [],
        "modules": [],
        "entity": None,
        "disclaimer": _DISCLAIMER,
    }


_EMAIL_SINGLE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
