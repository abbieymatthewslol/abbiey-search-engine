"""
Whitelisted OSINT modules — public DNS (DoH), RDAP, reverse DNS.

No authenticated paid intel APIs; no scraping of social sites.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from osint.schema import fact

logger = logging.getLogger(__name__)

_DOH_URL = "https://cloudflare-dns.com/dns-query"
_RDAP_DOMAIN = "https://rdap.org/domain/"
_RDAP_IP = "https://rdap.org/ip/"
_UA = "abbiey.search-osint/1.0 (+https://www.abbieysearch.com/privacy)"

_DNS_TYPES = ("A", "AAAA", "MX", "NS", "TXT")
_MAX_TXT_LEN = 220


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_domain(host: str) -> str | None:
    h = (host or "").strip().lower().rstrip(".")
    if not h or len(h) > 253:
        return None
    if h.startswith("http://") or h.startswith("https://"):
        try:
            from urllib.parse import urlparse

            p = urlparse(h if "://" in h else "https://" + h)
            h = (p.hostname or "").lower()
        except Exception:
            return None
    if not h or ".." in h:
        return None
    if not re.match(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", h):
        return None
    return h


def _validate_ipv4(s: str) -> str | None:
    try:
        ipaddress.IPv4Address(s.strip())
        return s.strip()
    except Exception:
        return None


def dns_facts(hostname: str, client: httpx.Client) -> list[dict[str, Any]]:
    """Resolve public DNS records via DNS-over-HTTPS (Cloudflare)."""
    host = _validate_domain(hostname)
    if not host:
        return []
    ts = _now_iso()
    out: list[dict[str, Any]] = []
    type_map = {1: "dns_a", 28: "dns_aaaa", 15: "dns_mx", 2: "dns_ns", 16: "dns_txt"}
    label_map = {
        "dns_a": "A",
        "dns_aaaa": "AAAA",
        "dns_mx": "MX",
        "dns_ns": "NS",
        "dns_txt": "TXT",
    }
    for rtype in _DNS_TYPES:
        try:
            r = client.get(
                _DOH_URL,
                params={"name": host, "type": rtype},
                headers={"accept": "application/dns-json", "User-Agent": _UA},
                timeout=6.0,
            )
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception:
            logger.debug("osint_doh_failed type=%s host=%s", rtype, host, exc_info=True)
            continue
        answers = data.get("Answer") or []
        if not isinstance(answers, list):
            continue
        for ans in answers:
            if not isinstance(ans, dict):
                continue
            t = ans.get("type")
            raw = ans.get("data")
            if raw is None:
                continue
            key = type_map.get(int(t) if isinstance(t, int) else -1)
            if not key:
                continue
            val = str(raw).strip().strip('"')
            if key == "dns_txt" and len(val) > _MAX_TXT_LEN:
                val = val[:_MAX_TXT_LEN] + "…"
            if key == "dns_mx" and val.startswith('"') and '"' in val[1:]:
                # DoH returns quoted "priority target"
                val = val.strip('"').replace('" "', " ", 1)
            out.append(
                fact(
                    type=key,
                    label=f"DNS {label_map.get(key, rtype)}",
                    value=val,
                    source="DNS (Cloudflare DNS-over-HTTPS)",
                    observed_at=ts,
                    confidence=0.9,
                    evidence_url="https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/",
                )
            )
    return out


def ptr_fact(ip: str) -> list[dict[str, Any]]:
    """PTR / reverse DNS via system resolver (best-effort)."""
    addr = _validate_ipv4(ip)
    if not addr:
        return []
    ts = _now_iso()
    try:
        host, _, _ = socket.gethostbyaddr(addr)
        if host:
            return [
                fact(
                    type="ptr",
                    label="Reverse DNS (PTR)",
                    value=host,
                    source="System DNS resolver",
                    observed_at=ts,
                    confidence=0.75,
                )
            ]
    except Exception:
        pass
    return []


def _rdap_events_entities(data: dict[str, Any]) -> tuple[str | None, list[str]]:
    lines: list[str] = []
    for ev in data.get("events") or []:
        if not isinstance(ev, dict):
            continue
        action = (ev.get("eventAction") or "").strip()
        when = (ev.get("eventDate") or "").strip()
        if action and when:
            lines.append(f"{action}: {when}")
    nss: list[str] = []
    for ns in data.get("nameservers") or []:
        if isinstance(ns, dict) and ns.get("ldhName"):
            nss.append(str(ns["ldhName"]).lower())
    return ("\n".join(lines[:12]) if lines else None), nss[:12]


def rdap_domain_facts(hostname: str, client: httpx.Client) -> list[dict[str, Any]]:
    host = _validate_domain(hostname)
    if not host:
        return []
    ts = _now_iso()
    url = _RDAP_DOMAIN + quote(host, safe=".")
    try:
        r = client.get(url, headers={"User-Agent": _UA, "Accept": "application/rdap+json"}, timeout=12.0)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        logger.debug("osint_rdap_domain_failed host=%s", host, exc_info=True)
        return []
    if not isinstance(data, dict):
        return []
    out: list[dict[str, Any]] = []
    status = data.get("status")
    if isinstance(status, list) and status:
        out.append(
            fact(
                type="rdap_status",
                label="RDAP domain status",
                value=", ".join(str(s) for s in status[:8]),
                source="RDAP",
                observed_at=ts,
                confidence=0.88,
                evidence_url=url,
            )
        )
    events_blob, nss = _rdap_events_entities(data)
    if events_blob:
        out.append(
            fact(
                type="rdap_events",
                label="RDAP events",
                value=events_blob.replace("\n", " · ")[:500],
                source="RDAP",
                observed_at=ts,
                confidence=0.85,
                evidence_url=url,
                detail=events_blob if len(events_blob) <= 800 else events_blob[:800] + "…",
            )
        )
    if nss:
        out.append(
            fact(
                type="rdap_ns",
                label="RDAP nameservers",
                value=", ".join(nss),
                source="RDAP",
                observed_at=ts,
                confidence=0.88,
                evidence_url=url,
            )
        )
    return out


def rdap_ip_facts(ip: str, client: httpx.Client) -> list[dict[str, Any]]:
    addr = _validate_ipv4(ip)
    if not addr:
        return []
    ts = _now_iso()
    url = _RDAP_IP + quote(addr, safe=":")
    try:
        r = client.get(url, headers={"User-Agent": _UA, "Accept": "application/rdap+json"}, timeout=12.0)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        logger.debug("osint_rdap_ip_failed ip=%s", addr, exc_info=True)
        return []
    if not isinstance(data, dict):
        return []
    out: list[dict[str, Any]] = []
    name = data.get("name") or data.get("handle")
    if name:
        out.append(
            fact(
                type="rdap_ip_net",
                label="RDAP network",
                value=str(name),
                source="RDAP",
                observed_at=ts,
                confidence=0.85,
                evidence_url=url,
            )
        )
    status = data.get("status")
    if isinstance(status, list) and status:
        out.append(
            fact(
                type="rdap_ip_status",
                label="RDAP IP status",
                value=", ".join(str(s) for s in status[:8]),
                source="RDAP",
                observed_at=ts,
                confidence=0.85,
                evidence_url=url,
            )
        )
    ents = data.get("entities") or []
    for ent in ents:
        if not isinstance(ent, dict):
            continue
        roles = ent.get("roles") or []
        if "abuse" not in roles:
            continue
        vcard = ent.get("vcardArray")
        if not (isinstance(vcard, list) and len(vcard) > 1):
            continue
        for row in vcard[1:]:
            if isinstance(row, list) and len(row) > 3 and row[0] == "tel":
                out.append(
                    fact(
                        type="rdap_abuse_contact",
                        label="RDAP abuse contact",
                        value=str(row[3])[:200],
                        source="RDAP",
                        observed_at=ts,
                        confidence=0.8,
                        evidence_url=url,
                    )
                )
                break
        break
    return out[:12]
