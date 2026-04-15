#!/usr/bin/env python3
"""
Normalize environment variables before pushing to Vercel or validating locally.

Enforces production defaults for this repo (abbieysearch.com + canonical Supabase project).
Returns a new dict; does not mutate the input.
"""
from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse, urlunparse


CANONICAL_SITE_URL = "https://abbieysearch.com"


def _strip_slash(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _supabase_ref_from_url(url: str) -> str:
    u = _strip_slash(url)
    m = re.match(r"^https?://([a-z0-9]+)\.supabase\.co$", u, re.I)
    return (m.group(1) if m else "").strip()


def _rewrite_db_user_if_needed(db_url: str, project_ref: str) -> tuple[str, bool]:
    """Transaction pooler (6543) must use postgres.<ref>, not bare postgres."""
    if not db_url or not project_ref:
        return db_url, False
    try:
        canonical = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        p = urlparse(canonical)
        host = (p.hostname or "").lower()
        user = unquote((p.username or "").strip())
        port = p.port or 5432
    except Exception:
        return db_url, False
    if port != 6543 or "pooler.supabase.com" not in host:
        return db_url, False
    if user == f"postgres.{project_ref}":
        return db_url, False
    if user != "postgres":
        return db_url, False
    password_raw = unquote(p.password or "")
    new_user = f"postgres.{project_ref}"
    auth = quote(new_user, safe="")
    if password_raw:
        auth += ":" + quote(password_raw, safe="")
    netloc = f"{auth}@{host}:{port}"
    new_p = p._replace(netloc=netloc)
    return urlunparse(new_p), True


def normalize_vercel_env_vars(
    raw: dict[str, str], *, enforce_site_url: bool = True
) -> tuple[dict[str, str], list[str]]:
    """
    Apply canonical SITE_URL, mirror NEXT_PUBLIC_* from server keys, fix pooler DB user.

    Returns (normalized_dict, list of human-readable changes).
    """
    out = dict(raw)
    notes: list[str] = []

    if enforce_site_url:
        out["SITE_URL"] = CANONICAL_SITE_URL
        notes.append(f"SITE_URL -> {CANONICAL_SITE_URL}")

    supabase_url = _strip_slash(out.get("SUPABASE_URL") or "")
    if supabase_url and not supabase_url.lower().startswith("https://"):
        supabase_url = "https://" + supabase_url.split("://", 1)[-1]
        out["SUPABASE_URL"] = supabase_url
        notes.append("SUPABASE_URL -> forced https scheme")
    ref = (out.get("ABBIEY_SUPABASE_PROJECT_REF") or "").strip() or _supabase_ref_from_url(supabase_url)
    if ref and supabase_url:
        expected = f"https://{ref}.supabase.co"
        if supabase_url.lower() != expected.lower():
            out["SUPABASE_URL"] = expected
            notes.append(f"SUPABASE_URL -> aligned to project ref {ref}")

    np_url = _strip_slash(out.get("NEXT_PUBLIC_SUPABASE_URL") or "")
    canonical_sb = _strip_slash(out.get("SUPABASE_URL") or "")
    if canonical_sb:
        if not np_url or np_url != canonical_sb:
            out["NEXT_PUBLIC_SUPABASE_URL"] = canonical_sb
            notes.append("NEXT_PUBLIC_SUPABASE_URL -> matched SUPABASE_URL")

    anon = (out.get("SUPABASE_ANON_KEY") or "").strip()
    np_anon = (out.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or "").strip()
    if anon and (not np_anon or np_anon != anon):
        out["NEXT_PUBLIC_SUPABASE_ANON_KEY"] = anon
        notes.append("NEXT_PUBLIC_SUPABASE_ANON_KEY -> matched SUPABASE_ANON_KEY")

    db_url = (out.get("SUPABASE_DB_URL") or out.get("DATABASE_URL") or "").strip()
    if db_url and ref:
        fixed, changed = _rewrite_db_user_if_needed(db_url, ref)
        if changed:
            out["SUPABASE_DB_URL"] = fixed
            if "DATABASE_URL" in out:
                out["DATABASE_URL"] = fixed
            notes.append(f"SUPABASE_DB_URL -> user postgres.{ref} for pooler:6543")

    return out, notes
