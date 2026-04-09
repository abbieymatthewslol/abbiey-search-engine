"""
Optional host-based lookups when Kali/Linux networking tools are on PATH.

Uses only validated domains/IPv4 — no shell, fixed argv, timeouts, output caps.
Disabled automatically when ``dig`` / ``whois`` are not installed (e.g. Vercel).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from typing import Any

from osint.modules import _now_iso, _validate_domain, _validate_ipv4
from osint.schema import fact

logger = logging.getLogger(__name__)

_MAX_DIG_LINES = 24
_MAX_WHOIS_CHARS = 4500
_DIG_TYPES_DOMAIN = ("A", "AAAA", "MX", "NS", "TXT")


def dig_available() -> bool:
    return shutil.which("dig") is not None


def whois_available() -> bool:
    return shutil.which("whois") is not None


def _run_cmd(argv: list[str], *, timeout: float) -> str | None:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug("kali_tools cmd failed argv=%s err=%s", argv, e)
        return None
    out = (proc.stdout or "").strip()
    return out or None


def dig_facts(hostname: str) -> list[dict[str, Any]]:
    """BIND dig +short for common record types (domain only)."""
    host = _validate_domain(hostname)
    if not host or not dig_available():
        return []
    ts = _now_iso()
    out: list[dict[str, Any]] = []
    for qtype in _DIG_TYPES_DOMAIN:
        raw = _run_cmd(
            ["dig", "+short", "+time=2", "+tries=1", qtype, host],
            timeout=8.0,
        )
        if not raw:
            continue
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()][: _MAX_DIG_LINES]
        if not lines:
            continue
        val = " · ".join(lines)
        if len(val) > 600:
            val = val[:597] + "…"
        out.append(
            fact(
                type=f"dig_{qtype.lower()}",
                label=f"dig {qtype}",
                value=val,
                source="system: dig (BIND DNS utility)",
                observed_at=ts,
                confidence=0.82,
            )
        )
    return out


def dig_reverse_facts(ip: str) -> list[dict[str, Any]]:
    """dig -x for PTR-style lookup via local resolver path."""
    addr = _validate_ipv4(ip)
    if not addr or not dig_available():
        return []
    ts = _now_iso()
    raw = _run_cmd(
        ["dig", "+short", "+time=2", "+tries=1", "-x", addr],
        timeout=8.0,
    )
    if not raw:
        return []
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()][:12]
    val = " · ".join(lines)
    return [
        fact(
            type="dig_ptr",
            label="dig reverse (-x)",
            value=val[:500],
            source="system: dig (BIND DNS utility)",
            observed_at=ts,
            confidence=0.78,
        )
    ]


def whois_facts(hostname: str) -> list[dict[str, Any]]:
    """Best-effort whois excerpt (domain); output varies by TLD / registrar."""
    host = _validate_domain(hostname)
    if not host or not whois_available():
        return []
    ts = _now_iso()
    raw = _run_cmd(["whois", host], timeout=14.0)
    if not raw:
        return []
    # Strip obvious noise; keep printable lines
    lines: list[str] = []
    for ln in raw.splitlines():
        s = ln.strip()
        if len(s) < 3 or s.startswith("%") or s.startswith("#"):
            continue
        if not re.match(r"^[\x20-\x7E]+$", s):
            continue
        lines.append(s)
        if len(lines) >= 48:
            break
    blob = "\n".join(lines)
    if len(blob) > _MAX_WHOIS_CHARS:
        blob = blob[: _MAX_WHOIS_CHARS - 1] + "…"
    return [
        fact(
            type="whois_excerpt",
            label="whois (excerpt)",
            value=blob.replace("\n", " · ")[:800],
            source="system: whois",
            observed_at=ts,
            confidence=0.65,
            detail=blob if len(blob) <= 2000 else blob[:1999] + "…",
        )
    ]
