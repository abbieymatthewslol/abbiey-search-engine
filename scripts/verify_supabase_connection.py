#!/usr/bin/env python3
"""Verify SUPABASE_DB_URL / DATABASE_URL — run from repo root: python scripts/verify_supabase_connection.py"""

import os
import sys

# Repo root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _normalize_supabase_db_url(db_url: str) -> str:
    if not db_url:
        return ""
    db_url = db_url.strip()
    try:
        from urllib.parse import urlparse

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


raw = (os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or "").strip()
url = _normalize_supabase_db_url(raw)
if not url:
    print("No SUPABASE_DB_URL or DATABASE_URL in environment.")
    print("Run:  python scripts/setup_supabase_env.py")
    print("(Uses your Supabase database password — not the sb_publishable_* API keys.)")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("Install deps: pip install -r requirements.txt")
    sys.exit(1)

try:
    conn = psycopg2.connect(url, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    finally:
        conn.close()
except Exception as e:
    print("Connection failed:", e)
    sys.exit(1)

print("OK — PostgreSQL reachable (Supabase connection string works).")
print("Start the app with: python app.py")
