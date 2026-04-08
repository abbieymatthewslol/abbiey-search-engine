#!/usr/bin/env python3
"""Verify Supabase pooler URL in .env — run from repo root."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT / ".env"


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _prefer_ipv4_pooler() -> None:
    """Windows often resolves Supabase pooler to IPv6 first; pooler may only respond on IPv4."""
    if sys.platform != "win32":
        return
    import socket

    _orig = socket.getaddrinfo

    def _ipv4(host, port, family=0, type=0, proto=0, flags=0):
        return _orig(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = _ipv4  # type: ignore[assignment]


try:
    from dotenv import load_dotenv

    load_dotenv(_ENV_FILE, override=True)
except ImportError:
    pass

_PROJECT_REF = (os.environ.get("ABBIEY_SUPABASE_PROJECT_REF") or "xwxscvllmghyogddpmii").strip()
_EXPECTED_POOLER_USER = f"postgres.{_PROJECT_REF}"


def _normalize_supabase_db_url(db_url: str) -> str:
    if not db_url:
        return ""
    db_url = db_url.strip()
    try:
        canonical = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        p = urlparse(canonical)
        host = (p.hostname or "").lower()
    except Exception:
        return db_url
    if not host or "supabase" not in host:
        return db_url
    if "sslmode=" in db_url.lower():
        return db_url
    sep = "&" if p.query else "?"
    return db_url + sep + "sslmode=require"


def _validate_pooler_url(db_url: str) -> tuple[bool, str]:
    if not db_url:
        return False, "No SUPABASE_DB_URL or DATABASE_URL. Run: python scripts/setup_supabase_env.py"

    try:
        canonical = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        p = urlparse(canonical)
        host = (p.hostname or "").lower()
        user = unquote((p.username or "").strip())
        port = p.port or 5432
    except Exception as e:
        return False, f"Unparseable database URL: {e}"

    if "pooler.supabase.com" not in host:
        return True, ""

    if port != 6543:
        return (
            False,
            f"Supabase pooler host {host!r} must use port 6543 (Transaction mode); got {port}. "
            "Run: python scripts/setup_supabase_env.py",
        )

    if user == "postgres":
        return (
            False,
            f"Invalid: user 'postgres' on pooler port 6543. Required user: {_EXPECTED_POOLER_USER}\n"
            "Run: python scripts/setup_supabase_env.py",
        )

    if not user.startswith("postgres.") or user != _EXPECTED_POOLER_USER:
        return (
            False,
            f"Pooler user must be {_EXPECTED_POOLER_USER}; got {user!r}.\n"
            "Run: python scripts/setup_supabase_env.py",
        )

    return True, ""


def main() -> int:
    _utf8_stdio()
    if not _ENV_FILE.is_file():
        print(f"Missing {_ENV_FILE}. Run: python scripts/setup_supabase_env.py")
        return 1

    raw = (os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or "").strip()
    url = _normalize_supabase_db_url(raw)

    ok, err = _validate_pooler_url(url)
    if not ok:
        print(err)
        return 1

    try:
        import psycopg2
    except ImportError:
        print("Install: pip install -r requirements.txt")
        return 1

    _prefer_ipv4_pooler()
    try:
        conn = psycopg2.connect(url, connect_timeout=10, client_encoding="UTF8")
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
    except Exception as e:
        print("Connection failed:", e)
        print("Confirm database password in Supabase Dashboard -> Settings -> Database.")
        return 1

    print(f"OK - pooler connection succeeded ({_EXPECTED_POOLER_USER} @ :6543).")
    print("Start: python app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
