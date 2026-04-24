"""Tests for scripts/vercel_env_normalize.py (production env shaping for Vercel)."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from vercel_env_normalize import normalize_vercel_env_vars  # noqa: E402


def test_site_url_and_mirrors():
    raw = {
        "SUPABASE_URL": "https://xwxscvllmghyogddpmii.supabase.co",
        "SUPABASE_ANON_KEY": "eyJ-test",
        "SITE_URL": "https://www.abbieysearch.com",
    }
    out, notes = normalize_vercel_env_vars(raw)
    assert out["SITE_URL"] == "https://abbieysearch.com"
    assert out["NEXT_PUBLIC_SUPABASE_URL"] == raw["SUPABASE_URL"]
    assert out["NEXT_PUBLIC_SUPABASE_ANON_KEY"] == "eyJ-test"
    assert any("SITE_URL" in n for n in notes)


def test_fix_pooler_db_user():
    raw = {
        "ABBIEY_SUPABASE_PROJECT_REF": "xwxscvllmghyogddpmii",
        "SUPABASE_URL": "https://xwxscvllmghyogddpmii.supabase.co",
        "SUPABASE_DB_URL": (
            "postgresql://postgres:p%40ss%2Fword@aws-1-ap-southeast-1.pooler.supabase.com:6543/postgres"
        ),
        "SUPABASE_ANON_KEY": "k",
    }
    out, notes = normalize_vercel_env_vars(raw)
    u = out["SUPABASE_DB_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
    p = urlparse(u)
    assert unquote(p.username or "") == "postgres.xwxscvllmghyogddpmii"
    assert unquote(p.password or "") == "p@ss/word"
    assert any("SUPABASE_DB_URL" in n for n in notes)


def test_skip_site_url_when_disabled():
    raw = {"SUPABASE_URL": "https://xwxscvllmghyogddpmii.supabase.co", "SITE_URL": "http://localhost:8000"}
    out, _ = normalize_vercel_env_vars(raw, enforce_site_url=False)
    assert out["SITE_URL"] == "http://localhost:8000"


@pytest.mark.parametrize(
    "bad,expected_host",
    [
        ("http://xwxscvllmghyogddpmii.supabase.co", "https://xwxscvllmghyogddpmii.supabase.co"),
    ],
)
def test_https_supabase_url(bad, expected_host):
    raw = {
        "ABBIEY_SUPABASE_PROJECT_REF": "xwxscvllmghyogddpmii",
        "SUPABASE_URL": bad,
        "SUPABASE_ANON_KEY": "k",
    }
    out, _ = normalize_vercel_env_vars(raw)
    assert out["SUPABASE_URL"] == expected_host
