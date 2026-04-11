"""
abbiey.search - A privacy-respecting, non-judgmental search engine.
No tracking. No filtering. No logs. Just results.
"""

import base64
import hashlib
import hmac
import json
from collections import Counter
import logging
import os
import re
import sys
import sqlite3
import subprocess
import threading
import time
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, wait as _futures_wait
from itertools import zip_longest
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, quote_plus, unquote, urlparse, urlencode

import feedparser
import httpx
import phonenumbers
from phonenumbers import NumberParseException
from cachetools import TTLCache
from ddgs import DDGS
from flask import Flask, render_template, request, jsonify, redirect, session, url_for, flash, Response, has_request_context, g
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from entity_parser import detect_entities, build_search_queries, primary_entity
from query_understanding import (
    preprocess_query,
    build_backend_search_query,
    resolve_location_for_search,
    query_ui_hints,
    should_enable_ai_summary,
    has_local_intent_signals,
    detect_query_clarification,
    is_simple_answer_query,
)
from retrieval.pipeline import run_text_retrieval_pipeline_sync
import digital_pet as _digital_pet
from osint.service import enrich as _osint_enrich_run
from osint.service import enrich_from_query as _osint_enrich_from_query
from osint.service import is_osint_enabled as _abbiey_osint_enabled

try:
    from dotenv import load_dotenv

    _env_root = os.path.dirname(os.path.abspath(__file__))
    # Single source of truth: .env overrides inherited shell vars for local dev.
    load_dotenv(os.path.join(_env_root, ".env"), override=True)
except ImportError:
    pass


def _resolve_flask_secret_key() -> str:
    """Secret for signing Flask sessions.

    On serverless, a fresh random key per cold start makes cookies from ``POST /auth/callback``
    unreadable on the next request (OAuth appears to fail after redirect). Prefer ``SECRET_KEY``
    in env; otherwise derive a stable key from the Postgres URL when running on a serverless host.
    """
    sk = (os.environ.get("SECRET_KEY") or "").strip()
    if sk:
        return sk
    serverless = bool(
        os.environ.get("VERCEL")
        or os.environ.get("RENDER")
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        or os.environ.get("K_SERVICE")
    )
    if serverless:
        for env_name in ("SUPABASE_DB_URL", "DATABASE_URL"):
            raw = (os.environ.get(env_name) or "").strip()
            if len(raw) >= 24:
                return hashlib.sha256(b"v1|flask-session|" + raw.encode("utf-8", errors="replace")).hexdigest()
        logging.getLogger(__name__).error(
            "Serverless without SECRET_KEY and without SUPABASE_DB_URL/DATABASE_URL: "
            "Flask sessions will not survive across instances. Set SECRET_KEY in environment."
        )
    return secrets.token_hex(24)


app = Flask(__name__)
app.config["SECRET_KEY"] = _resolve_flask_secret_key()
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000  # 1-year cache for static files
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("SITE_URL", "").startswith("https"):
    app.config["SESSION_COOKIE_SECURE"] = True

# Supabase Auth (JS SDK handled client-side; server validates JWT)
# Override for a different Supabase project (e.g. Vercel integration): ABBIEY_SUPABASE_PROJECT_REF + SUPABASE_URL
_ABBIEY_SUPABASE_PROJECT_REF = (os.environ.get("ABBIEY_SUPABASE_PROJECT_REF") or "xwxscvllmghyogddpmii").strip()
_ABBIEY_CANONICAL_SUPABASE_URL = f"https://{_ABBIEY_SUPABASE_PROJECT_REF}.supabase.co"
_RAW_SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip()
_SUPABASE_URL = _RAW_SUPABASE_URL.rstrip("/")
_SUPABASE_ANON_KEY = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
_SUPABASE_JWT_SECRET = (os.environ.get("SUPABASE_JWT_SECRET") or "").strip()
_SUPABASE_AUTH_ENABLED = bool(_SUPABASE_URL and _SUPABASE_ANON_KEY)
_SUPABASE_URL_ENFORCE = os.environ.get("RUNNING_PYTEST") != "1"


def _enforce_canonical_supabase_url(raw: str, normalized: str, label: str) -> None:
    if not normalized:
        return
    if "xwxcvllmghyogddpmii" in normalized:
        raise RuntimeError(
            f"{label} must not contain typo host xwxcvllmghyogddpmii (missing 's' in ref). "
            f"Expected project URL {_ABBIEY_CANONICAL_SUPABASE_URL!r}."
        )
    if normalized != _ABBIEY_CANONICAL_SUPABASE_URL:
        raise RuntimeError(
            f"{label} must match configured Supabase project (ABBIEY_SUPABASE_PROJECT_REF): "
            f"{_ABBIEY_CANONICAL_SUPABASE_URL!r} (no trailing slash). Got {raw!r}."
        )


if _SUPABASE_URL_ENFORCE:
    _enforce_canonical_supabase_url(_RAW_SUPABASE_URL, _SUPABASE_URL, "SUPABASE_URL")
    _np_raw = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").strip()
    _np = _np_raw.rstrip("/")
    if _np:
        _enforce_canonical_supabase_url(_np_raw, _np, "NEXT_PUBLIC_SUPABASE_URL")

try:
    from flask_compress import Compress
    Compress(app)
    app.config["COMPRESS_ALGORITHM"] = ["br", "gzip"]
    app.config["COMPRESS_MIN_SIZE"] = 500
except ImportError:
    pass

def _get_deploy_hash() -> str:
    """Return the current git commit hash baked into the running process."""
    # Prefer an env var set at build/deploy time (Render, Vercel, etc.)
    for env_var in ("RENDER_GIT_COMMIT", "VERCEL_GIT_COMMIT_SHA", "GIT_COMMIT"):
        val = os.environ.get(env_var, "")
        if val:
            return val[:7]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=os.path.dirname(__file__),
        ).decode().strip()
    except Exception:
        return "unknown"

DEPLOY_HASH = _get_deploy_hash()

# Google Search Console — HTML tag method. If GOOGLE_SITE_VERIFICATION is unset, the meta tag is omitted.
_GSC_DEFAULT_VERIFICATION = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()


def _load_google_site_verification() -> str:
    return _GSC_DEFAULT_VERIFICATION


_GOOGLE_SITE_VERIFICATION = _load_google_site_verification()

# Google Analytics 4 (gtag.js). If GOOGLE_ANALYTICS_ID is unset, the tag is omitted.
_GOOGLE_ANALYTICS_ID = os.environ.get("GOOGLE_ANALYTICS_ID", "").strip()

# On Vercel the filesystem is read-only except /tmp; use /tmp when running there.
_DB_DIR       = "/tmp" if os.environ.get("VERCEL") else os.path.dirname(__file__)
_WAITLIST_DB  = os.path.join(_DB_DIR, "waitlist.db")
_ANALYTICS_DB = os.path.join(_DB_DIR, "analytics.db")
_USERS_DB     = os.path.join(_DB_DIR, "users.db")

# Vercel /tmp is ephemeral per-invocation — all SQLite data is lost on cold start.
# Require a persistent DB backend when deploying to Vercel.
if os.environ.get("VERCEL"):
    _has_persistent_db = bool(
        os.environ.get("SUPABASE_DB_URL") or os.environ.get("LIBSQL_URL")
    )
    if not _has_persistent_db:
        raise RuntimeError(
            "Running on Vercel without a persistent database backend. "
            "Set SUPABASE_DB_URL or LIBSQL_URL to prevent data loss on cold starts."
        )
_ADMIN_TOKEN  = os.environ.get("ADMIN_TOKEN", "") or None  # None when unset → admin routes reject all requests

# Developer / API keys — Stripe Payment Link for purchasing access (override in env).
# These MUST be set via environment variables — no hardcoded defaults to avoid
# leaking live payment links into the public repo or forks.
STRIPE_API_KEYS_CHECKOUT_URL = os.environ.get("STRIPE_API_KEYS_CHECKOUT_URL", "")
STRIPE_SEARCH_CHECKOUT_URL = os.environ.get("STRIPE_SEARCH_CHECKOUT_URL", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
try:
    import stripe as _stripe_mod
except ImportError:
    _stripe_mod = None
ABBIEY_API_KEY_PREFIX = "abb_sk_live_"
_MAX_API_KEYS_PER_USER = 10


def _env_truthy(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on")


# Self-host only: disables all Flask-Limiter rules (public deployments should leave this off).
ABBIEY_OPEN_ACCESS = _env_truthy("ABBIEY_OPEN_ACCESS")


def _retrieval_pipeline_enabled() -> bool:
    """Multi-source async aggregation + scoring for web text search (read env per request for tests)."""
    return os.environ.get("ABBIEY_RETRIEVAL_PIPELINE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _max_query_length() -> int:
    raw = os.environ.get("ABBIEY_MAX_QUERY_LENGTH", "8000").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 8000
    return max(500, min(50000, n))


OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ---------------------------------------------------------------------------
# Feature gates — config-driven, no-redeploy toggles
# ---------------------------------------------------------------------------
# Each gate is read from an env var and controls who can access a feature:
#   "all"  — available to every visitor (default for all gates)
#   "paid" — available only to users with a paid/unlocked account
#   "none" — disabled for everyone (kill-switch)
_VALID_GATE_VALUES = frozenset(("all", "paid", "none"))

_FEATURE_GATES: dict[str, str] = {
    "deep_web":     os.environ.get("FEATURE_DEEP_WEB",     "all"),
    "ai_summary":   os.environ.get("FEATURE_AI_SUMMARY",   "all"),
    "answer_layer": os.environ.get("FEATURE_ANSWER_LAYER", "all"),
    "ai_chat":      os.environ.get("FEATURE_AI_CHAT",      "all"),
    "code_search":  os.environ.get("FEATURE_CODE_SEARCH",  "all"),
    "voice_search": os.environ.get("FEATURE_VOICE_SEARCH", "all"),
}


def _feature_allowed(name: str, unlocked: bool = False) -> bool:
    """Return True if *name* is accessible given the current user's unlock status."""
    val = _FEATURE_GATES.get(name, "all")
    if val not in _VALID_GATE_VALUES:
        val = "all"
    if val == "all":
        return True
    if val == "paid":
        return bool(unlocked)
    return False  # "none" — disabled for everyone


def _feature_gates_for_user(unlocked: bool) -> dict[str, bool]:
    """Return a dict of feature → bool for injection into template context."""
    return {name: _feature_allowed(name, unlocked) for name in _FEATURE_GATES}


def _site_base_url() -> str:
    """Canonical origin for OG tags, Twitter cards, JSON-LD, Stripe return URLs, and Supabase
    OAuth/password-reset redirectTo in templates (no trailing slash).
    Prefer SITE_URL or CANONICAL_URL in production so shares match your domain.
    Otherwise uses the current request origin (set SITE_URL if behind a proxy without X-Forwarded-*).
    """
    fixed = (os.environ.get("SITE_URL") or os.environ.get("CANONICAL_URL") or "").strip().rstrip("/")
    if fixed:
        return fixed
    try:
        if has_request_context():
            root = (request.url_root or "").rstrip("/")
            if root:
                return root
    except Exception:
        pass
    return "https://abbieysearch.com"


# Stable user-facing API messages (never put raw exceptions in JSON bodies).
_PREVIEW_MSG_INVALID = "That link cannot be previewed."
_PREVIEW_MSG_LONG = "That link is too long to preview."
_PREVIEW_MSG_ONION = "Previews for .onion addresses are not available here. Open the site in Tor Browser instead."
_PREVIEW_MSG_PRIVATE = "That address cannot be previewed."
_PREVIEW_MSG_TIMEOUT = "Preview timed out. The page may be slow or unreachable."
_PREVIEW_MSG_UNAVAILABLE = "We couldn't load a preview for this page."

_CHAT_MSG_MISSING = "Run a search first, then ask a question in the research assistant."
_CHAT_MSG_QUERY_LONG = "That search is too long for the assistant. Try a shorter query."
_CHAT_MSG_MESSAGE_LONG = "That message is too long. Please shorten it and try again."
_CHAT_MSG_HISTORY = "Something went wrong with the conversation. Refresh the page and try again."
_CHAT_MSG_UNAVAILABLE = "The research assistant is temporarily unavailable. Please try again in a moment."
_AI_SUMMARY_MSG_UNAVAILABLE = "Summary is temporarily unavailable. Results are shown below."
_AI_SUMMARY_MSG_NO_CONTEXT = "Summary is unavailable because there were not enough results to summarize yet."
_RATE_LIMIT_MSG = "Too many requests. Please wait a moment and try again."
_ONION_FALLBACK_MSG = (
    "Ahmia is temporarily unavailable, so these results come from a web fallback and may reference "
    "onion sites rather than link to them directly."
)
_ONION_UNAVAILABLE_MSG = (
    "Deep web search is temporarily degraded. Ahmia could not be reached and the fallback returned no results."
)
_SEARCH_UNLOCK_COOKIE = "abbiey_search_unlock"
_SEARCH_UNLOCK_COOKIE_MAX_AGE = 315360000
_WELCOME_COOKIE = "abbiey_welcome_seen"
_WELCOME_COOKIE_MAX_AGE = 60 * 60 * 24 * 400  # ~13 months — first-visit onboarding
_SB_ACCESS_TOKEN_COOKIE = "sb_access_token"
_SB_ACCESS_TOKEN_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
_SEARCH_CHECKOUT_PENDING_SESSION_KEY = "abbiey_search_checkout_started_at"
_SEARCH_CHECKOUT_PENDING_WINDOW_SECONDS = 4 * 60 * 60
_SEARCH_CHECKOUT_PENDING_COOKIE = "abbiey_search_checkout_pending"
_SEARCH_CHECKOUT_PENDING_COOKIE_MAX_AGE = 4 * 60 * 60
_SERVER_FREE_SEARCH_LIMIT = int(os.environ.get("ABBIEY_FREE_SEARCH_LIMIT", "15"))

# In-memory daily search counter per IP (reset daily; supplements client-side limit)
_search_counter_lock = threading.Lock()
_search_counters: dict[str, dict] = {}  # ip -> {"count": int, "date": str}

# ---------------------------------------------------------------------------
# Turso / libSQL persistent DB (optional upgrade — survives Vercel cold starts)
# Set LIBSQL_URL=https://xxx.turso.io and LIBSQL_AUTH_TOKEN=<token> in Vercel
# env vars to enable.  Falls back to local SQLite automatically.
# ---------------------------------------------------------------------------
_LIBSQL_URL   = os.environ.get("LIBSQL_URL", "").rstrip("/")
_LIBSQL_TOKEN = os.environ.get("LIBSQL_AUTH_TOKEN", "")


def _turso_execute(sql: str, args: list = None, db: str = "analytics") -> list:
    """Execute a SQL statement against Turso/libSQL HTTP API.
    Returns list of row dicts on SELECT, empty list on write.
    Raises on error.
    """
    url = f"{_LIBSQL_URL}/v2/pipeline"
    if db == "users" and os.environ.get("LIBSQL_USERS_URL"):
        url = os.environ.get("LIBSQL_USERS_URL", "").rstrip("/") + "/v2/pipeline"
    stmt: dict = {"sql": sql}
    if args:
        stmt["args"] = [
            {"type": "text", "value": str(a)} if isinstance(a, str)
            else {"type": "integer", "value": int(a)} if isinstance(a, int)
            else {"type": "null"} if a is None
            else {"type": "text", "value": str(a)}
            for a in args
        ]
    payload = {"requests": [{"type": "execute", "stmt": stmt}, {"type": "close"}]}
    import httpx as _hx
    resp = _hx.post(url, json=payload,
                    headers={"Authorization": f"Bearer {_LIBSQL_TOKEN}"},
                    timeout=8)
    resp.raise_for_status()
    data = resp.json()
    result = data["results"][0]
    if result.get("type") == "error":
        raise RuntimeError(result["error"]["message"])
    rows_data = result.get("response", {}).get("result", {})
    cols = [c["name"] for c in rows_data.get("cols", [])]
    rows = []
    for raw_row in rows_data.get("rows", []):
        rows.append({cols[i]: (v.get("value") if v.get("type") != "null" else None)
                     for i, v in enumerate(raw_row)})
    return rows


# ---------------------------------------------------------------------------
# Supabase / PostgreSQL persistent backend (alternative to Turso)
#
# This app uses PostgreSQL via psycopg2, NOT the Supabase REST/Data API keys
# (sb_publishable_* / sb_secret_*). In Supabase Dashboard:
#   Settings → Database → Connection string → URI (use "Transaction" pooler for
#   serverless, port 6543, or direct connection port 5432).
# Set either SUPABASE_DB_URL or DATABASE_URL to that postgres:// or postgresql:// URI.
# ---------------------------------------------------------------------------


def _normalize_supabase_db_url(db_url: str) -> str:
    """Append sslmode=require for Supabase hosts when omitted (psycopg2 / some networks need it)."""
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


_SUPABASE_DB_URL = _normalize_supabase_db_url(
    os.environ.get("SUPABASE_DB_URL", "") or os.environ.get("DATABASE_URL", "")
)


def _fatal_if_invalid_pooler_db_url(db_url: str) -> None:
    if not db_url or "pooler.supabase.com" not in db_url.lower():
        return
    try:
        u = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        p = urlparse(u)
        user = unquote((p.username or "").strip())
        port = p.port or 5432
    except Exception:
        return
    if port == 6543 and user == "postgres":
        logging.getLogger(__name__).error(
            "Invalid DB URL: Transaction pooler (port 6543) must use user "
            f"postgres.{_ABBIEY_SUPABASE_PROJECT_REF}, not 'postgres'. "
            "Run: python scripts/setup_supabase_env.py"
        )
        sys.exit(1)


_fatal_if_invalid_pooler_db_url(_SUPABASE_DB_URL)

# True only after table init + ping succeed; avoids 500s when URL is set but DB is unreachable.
_SUPABASE_DB_READY = False
_pg_conn_lock = threading.Lock()


def _db_url_host_for_log(db_url: str) -> str:
    """Return host:port for logs and health JSON (never the password)."""
    if not db_url:
        return ""
    try:
        u = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        p = urlparse(u)
        if not p.hostname:
            return "(invalid URL)"
        port = p.port or 5432
        return f"{p.hostname}:{port}"
    except Exception:
        return "(unparseable URL)"


def _adapt_sql_pg(sql: str) -> str:
    """Translate SQLite-specific SQL to PostgreSQL equivalents."""
    import re as _re
    # datetime('now', '-N days/hours/minutes') → NOW() - INTERVAL 'N unit'
    sql = _re.sub(r"datetime\('now',\s*'-(\d+) (days?|hours?|minutes?)'\)",
                  r"NOW() - INTERVAL '\1 \2'", sql)
    # datetime('now') → NOW()
    sql = _re.sub(r"datetime\('now'\)", "NOW()", sql)
    # date('now') → CURRENT_DATE
    sql = _re.sub(r"date\('now'\)", "CURRENT_DATE", sql)
    # date(col) → DATE(col)
    sql = _re.sub(r"\bdate\((\w+)\)", r"DATE(\1)", sql)
    # strftime('%H:%M', col) → TO_CHAR(col, 'HH24:MI')
    sql = _re.sub(r"strftime\('%H:%M',\s*(\w+)\)", r"TO_CHAR(\1, 'HH24:MI')", sql)
    # strftime('%Y-%m-%d', col) → TO_CHAR(col, 'YYYY-MM-DD')
    sql = _re.sub(r"strftime\('%Y-%m-%d',\s*(\w+)\)", r"TO_CHAR(\1, 'YYYY-MM-DD')", sql)
    # INSERT OR IGNORE → INSERT … ON CONFLICT DO NOTHING
    _was_or_ignore = bool(_re.search(r'\bINSERT\s+OR\s+IGNORE\b', sql, _re.IGNORECASE))
    sql = _re.sub(r'\bINSERT\s+OR\s+IGNORE\b', 'INSERT', sql, flags=_re.IGNORECASE)
    # AUTOINCREMENT → not needed with SERIAL; remove it
    sql = _re.sub(r'\bAUTOINCREMENT\b', '', sql, flags=_re.IGNORECASE)
    # COLLATE NOCASE → PostgreSQL doesn't use this; strip it
    sql = _re.sub(r'\bCOLLATE\s+NOCASE\b', '', sql, flags=_re.IGNORECASE)
    # Append ON CONFLICT DO NOTHING for converted INSERT OR IGNORE
    # Must go *after* RETURNING clause if present
    if _was_or_ignore and 'ON CONFLICT' not in sql.upper():
        returning_match = _re.search(r'\bRETURNING\b.*', sql, _re.IGNORECASE)
        if returning_match:
            # Insert ON CONFLICT DO NOTHING before RETURNING
            pos = returning_match.start()
            sql = sql[:pos].rstrip() + ' ON CONFLICT DO NOTHING ' + sql[pos:]
        else:
            sql = sql.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
    return sql


def _pg_execute(sql: str, args: list = None) -> list:
    """Execute SQL against PostgreSQL (Supabase). Returns list of row dicts."""
    import psycopg2
    import psycopg2.extras
    pg_sql = _adapt_sql_pg(sql)
    # Use %s placeholders for psycopg2 (SQLite uses ?)
    pg_sql = pg_sql.replace("?", "%s")
    conn = psycopg2.connect(_SUPABASE_DB_URL, connect_timeout=8,
                            options="-c statement_timeout=10000")
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(pg_sql, args or [])
            # Fetch before commit — committing first can discard RETURNING / result rows (breaks signup INSERT … RETURNING id).
            rows_out = []
            if cur.description is not None:
                rows_out = [dict(row) for row in cur.fetchall()]
            conn.commit()
            return rows_out
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _init_pg_tables():
    """Create all app tables in PostgreSQL (Supabase) if they don't exist."""
    ddl = """
        CREATE TABLE IF NOT EXISTS search_logs (
            id          SERIAL PRIMARY KEY,
            query       TEXT NOT NULL,
            search_type TEXT DEFAULT 'text',
            region      TEXT DEFAULT '',
            result_count INTEGER DEFAULT 0,
            latency_ms  INTEGER DEFAULT 0,
            hour        INTEGER DEFAULT 0,
            day_of_week INTEGER DEFAULT 0,
            client_ip   TEXT DEFAULT '',
            user_agent  TEXT DEFAULT '',
            device_label TEXT DEFAULT '',
            location    TEXT DEFAULT '',
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_sl_created ON search_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_sl_query   ON search_logs(query);

        CREATE TABLE IF NOT EXISTS error_logs (
            id         SERIAL PRIMARY KEY,
            route      TEXT DEFAULT '',
            level      TEXT DEFAULT 'error',
            message    TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_el_created ON error_logs(created_at);

        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name  TEXT,
            bio           TEXT DEFAULT '',
            avatar        TEXT,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            last_seen     TIMESTAMPTZ DEFAULT NOW(),
            email_verified BOOLEAN NOT NULL DEFAULT TRUE,
            verify_token  TEXT,
            verify_token_expires TIMESTAMPTZ,
            otp_code_hash TEXT,
            otp_expires   TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(LOWER(username));
        CREATE INDEX IF NOT EXISTS idx_users_email    ON users(LOWER(email));

        CREATE TABLE IF NOT EXISTS user_bookmarks (
            id       SERIAL PRIMARY KEY,
            user_id  INTEGER NOT NULL,
            url      TEXT NOT NULL,
            title    TEXT,
            snippet  TEXT,
            saved_at TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, url)
        );
        CREATE INDEX IF NOT EXISTS idx_ub_user ON user_bookmarks(user_id);

        CREATE TABLE IF NOT EXISTS user_search_history (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            query       TEXT NOT NULL,
            search_type TEXT DEFAULT 'text',
            searched_at TIMESTAMPTZ DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ush_user ON user_search_history(user_id);

        CREATE TABLE IF NOT EXISTS api_keys (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            label         TEXT NOT NULL DEFAULT '',
            key_last_four TEXT NOT NULL,
            key_hash      TEXT NOT NULL,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            revoked_at    TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);

        CREATE TABLE IF NOT EXISTS search_unlocks (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER REFERENCES users(id) ON DELETE CASCADE,
            unlock_token TEXT UNIQUE NOT NULL,
            source       TEXT NOT NULL DEFAULT 'payment_return',
            created_at   TIMESTAMPTZ DEFAULT NOW(),
            last_seen    TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_search_unlocks_user ON search_unlocks(user_id);

        CREATE TABLE IF NOT EXISTS pending_checkouts (
            id              SERIAL PRIMARY KEY,
            checkout_token  TEXT UNIQUE NOT NULL,
            user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
            client_ip       TEXT DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'pending',
            created_at      TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_pc_token ON pending_checkouts(checkout_token);

        CREATE TABLE IF NOT EXISTS payment_events (
            id                  SERIAL PRIMARY KEY,
            stripe_event_id     TEXT UNIQUE,
            stripe_session_id   TEXT,
            checkout_token      TEXT,
            customer_email      TEXT DEFAULT '',
            amount_cents        INTEGER DEFAULT 0,
            currency            TEXT DEFAULT 'usd',
            status              TEXT NOT NULL DEFAULT 'completed',
            created_at          TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_pe_checkout ON payment_events(checkout_token);

        CREATE TABLE IF NOT EXISTS waitlist (
            id         SERIAL PRIMARY KEY,
            email      TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS user_pet (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            species TEXT NOT NULL DEFAULT 'hummingbird',
            xp_total INTEGER NOT NULL DEFAULT 0,
            last_activity_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT chk_user_pet_species CHECK (
                species IN ('hummingbird', 'firefly', 'snake', 'dolphin')
            )
        );
        CREATE INDEX IF NOT EXISTS idx_user_pet_xp ON user_pet (xp_total DESC);

        CREATE TABLE IF NOT EXISTS pet_activity_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            xp INTEGER NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_pal_user_time ON pet_activity_log (user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS pet_daily_xp (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            day_utc TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day_utc)
        );
    """
    try:
        _pg_execute(ddl)
    except Exception as exc:
        logging.warning("PG table init failed: %s", exc)


def _migrate_pg_users_lower_unique():
    """Enforce case-insensitive uniqueness on Postgres (aligns with SQLite COLLATE NOCASE)."""
    if not _SUPABASE_DB_URL:
        return
    for stmt in (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_lower ON users ((LOWER(username)))",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users ((LOWER(email)))",
    ):
        try:
            _pg_execute(stmt, [])
        except Exception as exc:
            logging.warning("PG users lower-unique index skipped: %s", exc)


if _SUPABASE_DB_URL:
    try:
        _init_pg_tables()
        _migrate_pg_users_lower_unique()
        _pg_execute("SELECT 1 AS ok")
        _endpoint = _db_url_host_for_log(_SUPABASE_DB_URL)
        _SUPABASE_DB_READY = True
        logging.info("Supabase/PostgreSQL connected (%s) — users, analytics, waitlist use this DB", _endpoint)
    except Exception as _pg_init_err:
        logging.warning(
            "Supabase/PostgreSQL connection failed (%s): %s",
            _db_url_host_for_log(_SUPABASE_DB_URL),
            _pg_init_err,
        )


def _analytics_execute(sql: str, args: list = None):
    """Route SQL to the active analytics backend: Supabase → Turso → SQLite."""
    if _SUPABASE_DB_URL and _SUPABASE_DB_READY:
        return _pg_execute(sql, args or [])
    if _LIBSQL_URL and _LIBSQL_TOKEN:
        return _turso_execute(sql, args or [], db="analytics")
    with sqlite3.connect(_ANALYTICS_DB) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, args or [])
        if cur.description:
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        return []


def _active_storage() -> str:
    if _SUPABASE_DB_URL and _SUPABASE_DB_READY:
        return "supabase"
    if _LIBSQL_URL and _LIBSQL_TOKEN:
        return "turso"
    return "sqlite_tmp"


# ---------------------------------------------------------------------------
# SSE live broadcast queue — receives events from _log_search
# ---------------------------------------------------------------------------
_SSE_CLIENTS: list = []  # list of queue.Queue objects, one per connected admin
_SSE_LOCK = threading.Lock()


def _sse_broadcast(event: dict):
    """Push a JSON event to all connected SSE clients."""
    data = json.dumps(event)
    with _SSE_LOCK:
        dead = []
        for q in _SSE_CLIENTS:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            _SSE_CLIENTS.remove(q)


def _init_waitlist_db():
    with sqlite3.connect(_WAITLIST_DB) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS waitlist "
            "(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, created_at TEXT DEFAULT (datetime('now')))"
        )
_init_waitlist_db()


# ---------------------------------------------------------------------------
# Analytics DB
# ---------------------------------------------------------------------------
def _init_analytics_db():
    with sqlite3.connect(_ANALYTICS_DB) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS search_logs ("
            "  id INTEGER PRIMARY KEY,"
            "  query TEXT NOT NULL,"
            "  search_type TEXT DEFAULT 'text',"
            "  region TEXT DEFAULT '',"
            "  result_count INTEGER DEFAULT 0,"
            "  latency_ms INTEGER DEFAULT 0,"
            "  hour INTEGER DEFAULT 0,"
            "  day_of_week INTEGER DEFAULT 0,"
            "  created_at TEXT DEFAULT (datetime('now'))"
            ")"
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_sl_created ON search_logs(created_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sl_query   ON search_logs(query)")
        # Add latency_ms column to existing tables (idempotent)
        try:
            con.execute("ALTER TABLE search_logs ADD COLUMN latency_ms INTEGER DEFAULT 0")
        except Exception:
            pass
        # Error log table
        con.execute(
            "CREATE TABLE IF NOT EXISTS error_logs ("
            "  id INTEGER PRIMARY KEY,"
            "  route TEXT DEFAULT '',"
            "  level TEXT DEFAULT 'error',"
            "  message TEXT NOT NULL,"
            "  created_at TEXT DEFAULT (datetime('now'))"
            ")"
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_el_created ON error_logs(created_at)")
        for _col in ("client_ip", "user_agent", "device_label", "location"):
            try:
                con.execute(f"ALTER TABLE search_logs ADD COLUMN {_col} TEXT DEFAULT ''")
            except Exception:
                pass


_init_analytics_db()


def _migrate_search_logs_client_columns():
    """Add client_ip, user_agent, device_label, location to search_logs (all analytics backends)."""
    if _SUPABASE_DB_URL and _SUPABASE_DB_READY:
        for stmt in (
            "ALTER TABLE search_logs ADD COLUMN IF NOT EXISTS client_ip TEXT DEFAULT ''",
            "ALTER TABLE search_logs ADD COLUMN IF NOT EXISTS user_agent TEXT DEFAULT ''",
            "ALTER TABLE search_logs ADD COLUMN IF NOT EXISTS device_label TEXT DEFAULT ''",
            "ALTER TABLE search_logs ADD COLUMN IF NOT EXISTS location TEXT DEFAULT ''",
        ):
            try:
                _pg_execute(stmt, [])
            except Exception:
                pass
        return
    if _LIBSQL_URL and _LIBSQL_TOKEN:
        for _col in ("client_ip", "user_agent", "device_label", "location"):
            try:
                _turso_execute(
                    f"ALTER TABLE search_logs ADD COLUMN {_col} TEXT DEFAULT ''",
                    [], db="analytics",
                )
            except Exception:
                pass
        return
    try:
        with sqlite3.connect(_ANALYTICS_DB) as con:
            for _col in ("client_ip", "user_agent", "device_label", "location"):
                try:
                    con.execute(f"ALTER TABLE search_logs ADD COLUMN {_col} TEXT DEFAULT ''")
                except Exception:
                    pass
            con.commit()
    except Exception:
        pass


try:
    _migrate_search_logs_client_columns()
except Exception as _mig_err:
    logging.warning("search_logs client columns migration: %s", _mig_err)


def _users_execute(sql: str, args: list = None, return_id: bool = False) -> list:
    """Route SQL to Supabase or users.db SQLite. When return_id=True, returns [{'id': N}]."""
    if _SUPABASE_DB_URL and _SUPABASE_DB_READY:
        if return_id and sql.strip().upper().startswith('INSERT'):
            pg_sql = sql.rstrip().rstrip(';') + ' RETURNING id'
            return _pg_execute(pg_sql, args)
        return _pg_execute(sql, args)
    with sqlite3.connect(_USERS_DB) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, args or [])
        if return_id:
            return [{"id": cur.lastrowid}]
        if cur.description:
            return [dict(r) for r in cur.fetchall()]
        return []


def _waitlist_execute(sql: str, args: list = None) -> list:
    """Route SQL to Supabase or waitlist.db SQLite."""
    if _SUPABASE_DB_URL and _SUPABASE_DB_READY:
        return _pg_execute(sql, args)
    with sqlite3.connect(_WAITLIST_DB) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, args or [])
        if cur.description:
            return [dict(r) for r in cur.fetchall()]
        return []


# ---------------------------------------------------------------------------
# Users DB
# ---------------------------------------------------------------------------
def _init_users_db():
    with sqlite3.connect(_USERS_DB) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL COLLATE NOCASE,
                email         TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                display_name  TEXT,
                bio           TEXT DEFAULT '',
                created_at    TEXT DEFAULT (datetime('now')),
                last_seen     TEXT DEFAULT (datetime('now')),
                email_verified INTEGER DEFAULT 1,
                verify_token TEXT,
                verify_token_expires TEXT,
                otp_code_hash TEXT,
                otp_expires TEXT
            );
            CREATE TABLE IF NOT EXISTS user_bookmarks (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                url      TEXT NOT NULL,
                title    TEXT,
                snippet  TEXT,
                saved_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id, url)
            );
            CREATE TABLE IF NOT EXISTS user_search_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                query       TEXT NOT NULL,
                search_type TEXT DEFAULT 'text',
                searched_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_ub_user  ON user_bookmarks(user_id);
            CREATE INDEX IF NOT EXISTS idx_ush_user ON user_search_history(user_id);
            CREATE TABLE IF NOT EXISTS api_keys (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                label         TEXT NOT NULL DEFAULT '',
                key_last_four TEXT NOT NULL,
                key_hash      TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now')),
                revoked_at    TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
            CREATE TABLE IF NOT EXISTS search_unlocks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER,
                unlock_token TEXT UNIQUE NOT NULL,
                source       TEXT NOT NULL DEFAULT 'payment_return',
                created_at   TEXT DEFAULT (datetime('now')),
                last_seen    TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_search_unlocks_user ON search_unlocks(user_id);

            CREATE TABLE IF NOT EXISTS pending_checkouts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                checkout_token  TEXT UNIQUE NOT NULL,
                user_id         INTEGER,
                client_ip       TEXT DEFAULT '',
                status          TEXT NOT NULL DEFAULT 'pending',
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pc_token ON pending_checkouts(checkout_token);

            CREATE TABLE IF NOT EXISTS payment_events (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                stripe_event_id     TEXT UNIQUE,
                stripe_session_id   TEXT,
                checkout_token      TEXT,
                customer_email      TEXT DEFAULT '',
                amount_cents        INTEGER DEFAULT 0,
                currency            TEXT DEFAULT 'usd',
                status              TEXT NOT NULL DEFAULT 'completed',
                created_at          TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_pe_checkout ON payment_events(checkout_token);

            CREATE TABLE IF NOT EXISTS user_pet (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                species TEXT NOT NULL DEFAULT 'hummingbird',
                xp_total INTEGER NOT NULL DEFAULT 0,
                last_activity_at TEXT DEFAULT (datetime('now')),
                created_at TEXT DEFAULT (datetime('now')),
                CHECK (species IN ('hummingbird', 'firefly', 'snake', 'dolphin'))
            );
            CREATE INDEX IF NOT EXISTS idx_user_pet_xp ON user_pet (xp_total DESC);

            CREATE TABLE IF NOT EXISTS pet_activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                action TEXT NOT NULL,
                xp INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_pal_user_time ON pet_activity_log (user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS pet_daily_xp (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                day_utc TEXT NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day_utc)
            );
        """)


def _migrate_users_email_verification_columns():
    """Add email verification columns to existing SQLite / Postgres users tables."""
    sqlite_alters = (
        "ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN verify_token TEXT",
        "ALTER TABLE users ADD COLUMN verify_token_expires TEXT",
        "ALTER TABLE users ADD COLUMN otp_code_hash TEXT",
        "ALTER TABLE users ADD COLUMN otp_expires TEXT",
    )
    for stmt in sqlite_alters:
        try:
            with sqlite3.connect(_USERS_DB) as con:
                con.execute(stmt)
        except Exception:
            pass
    if not (_SUPABASE_DB_URL and _SUPABASE_DB_READY):
        return
    pg_alters = (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verify_token TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verify_token_expires TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_code_hash TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_expires TIMESTAMPTZ",
    )
    for stmt in pg_alters:
        try:
            _pg_execute(stmt, [])
        except Exception as exc:
            logging.warning("PG users email verification migration: %s", exc)


_init_users_db()
_migrate_users_email_verification_columns()


def _migrate_users_phone_column():
    """Optional E.164 phone on user profile (signup + OAuth sync)."""
    try:
        with sqlite3.connect(_USERS_DB) as con:
            con.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    except Exception:
        pass
    if _SUPABASE_DB_URL and _SUPABASE_DB_READY:
        try:
            _pg_execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT", [])
        except Exception as exc:
            logging.warning("PG users phone migration: %s", exc)


_migrate_users_phone_column()

# Avatar column migration — SQLite only (PG schema already includes it)
if not _SUPABASE_DB_URL:
    try:
        with sqlite3.connect(_USERS_DB) as _con:
            _con.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
    except Exception:
        pass  # Column already exists

# Ensure avatars upload directory exists (not on Vercel)
_AVATARS_DIR = os.path.join(os.path.dirname(__file__), "static", "avatars")
if not os.environ.get("VERCEL"):
    os.makedirs(_AVATARS_DIR, exist_ok=True)


def _session_user_id_int(uid) -> int | None:
    """Coerce session user_id to int; corrupt cookies must not 500 the app."""
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None


def _row_returning_id(rows: list | None) -> int | None:
    """Read SERIAL id from INSERT … RETURNING (RealDict key may vary by driver)."""
    if not rows:
        return None
    r = rows[0]
    if r.get("id") is not None:
        try:
            return int(r["id"])
        except (TypeError, ValueError):
            pass
    for k, v in r.items():
        if str(k).lower() == "id" and v is not None:
            try:
                return int(v)
            except (TypeError, ValueError):
                return None
    return None


def _search_unlock_cookie_token() -> str | None:
    raw = (request.cookies.get(_SEARCH_UNLOCK_COOKIE) or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"[A-Za-z0-9_-]{20,120}", raw):
        return raw
    return None


def _set_search_unlock_cookie(resp: Response, token: str) -> None:
    secure = request.is_secure or _site_base_url().startswith("https://")
    resp.set_cookie(
        _SEARCH_UNLOCK_COOKIE,
        token,
        max_age=_SEARCH_UNLOCK_COOKIE_MAX_AGE,
        secure=secure,
        httponly=True,
        samesite="Lax",
        path="/",
    )


def _set_welcome_seen_cookie(resp: Response) -> None:
    """Mark browser as having completed or skipped first-visit onboarding."""
    secure = request.is_secure or _site_base_url().startswith("https://")
    resp.set_cookie(
        _WELCOME_COOKIE,
        "1",
        max_age=_WELCOME_COOKIE_MAX_AGE,
        secure=secure,
        httponly=False,
        samesite="Lax",
        path="/",
    )


def _set_sb_access_token_cookie(resp: Response, token: str) -> None:
    """Store the Supabase access token as a secure HTTP-only cookie."""
    secure = request.is_secure or _site_base_url().startswith("https://")
    resp.set_cookie(
        _SB_ACCESS_TOKEN_COOKIE,
        token,
        max_age=_SB_ACCESS_TOKEN_COOKIE_MAX_AGE,
        secure=secure,
        httponly=True,
        samesite="Lax",
        path="/",
    )


def _uid_from_sb_access_token_cookie() -> int | None:
    """Resolve Flask user id from the Supabase access token HTTP-only cookie.

    Decodes the JWT payload (base64url middle segment) to extract the ``email``
    claim, then looks up the matching user in our database.  No signature
    verification is performed here — the cookie is HTTP-only and was set
    server-side only after a successful Supabase auth exchange.
    """
    raw = (request.cookies.get(_SB_ACCESS_TOKEN_COOKIE) or "").strip()
    if not raw:
        return None
    try:
        parts = raw.split(".")
        if len(parts) != 3:
            return None
        padding = 4 - len(parts[1]) % 4
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * padding))
        email = (payload.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return None
        rows = _users_execute(
            "SELECT id FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1", [email]
        )
        if not rows:
            return None
        return _session_user_id_int(rows[0]["id"])
    except Exception:
        logger.debug("sb_access_token_cookie_decode_failed", exc_info=True)
        return None
    """Return E.164 (e.g. +15551234567) or None if invalid / empty."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        parsed = phonenumbers.parse(s, default_region if not s.startswith("+") else None)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        return None


def _checkout_hmac_key() -> bytes:
    """Derive HMAC key for checkout-pending cookies from Flask SECRET_KEY."""
    sk = (app.config.get("SECRET_KEY") or app.secret_key or "").strip()
    return hmac.new(sk.encode("utf-8", errors="replace"), b"abbiey-checkout-pending", hashlib.sha256).digest()


def _search_checkout_pending() -> bool:
    # Check session first (original approach)
    raw = session.get(_SEARCH_CHECKOUT_PENDING_SESSION_KEY)
    try:
        started = float(raw)
    except (TypeError, ValueError):
        started = None
    if started and (time.time() - started) <= _SEARCH_CHECKOUT_PENDING_WINDOW_SECONDS:
        return True
    # Fallback: check signed cookie (survives session loss across redeploys)
    cookie_val = request.cookies.get(_SEARCH_CHECKOUT_PENDING_COOKIE, "")
    if cookie_val:
        parts = cookie_val.split(".", 1)
        if len(parts) == 2:
            ts_str, sig = parts
            try:
                ts = float(ts_str)
            except (TypeError, ValueError):
                return False
            expected = hmac.new(
                _checkout_hmac_key(), ts_str.encode(), hashlib.sha256
            ).hexdigest()[:16]
            if hmac.compare_digest(sig, expected) and (time.time() - ts) <= _SEARCH_CHECKOUT_PENDING_WINDOW_SECONDS:
                return True
    return False


def _search_access_token_for_user(uid: int | None) -> str | None:
    if not uid:
        return None
    rows = _users_execute(
        "SELECT unlock_token FROM search_unlocks WHERE user_id=? ORDER BY id DESC LIMIT 1",
        [uid],
    )
    token = (rows[0].get("unlock_token") if rows else "") or ""
    return token.strip() or None


def _search_access_granted(uid: int | None = None, token: str | None = None) -> bool:
    if uid:
        rows = _users_execute("SELECT 1 AS ok FROM search_unlocks WHERE user_id=? LIMIT 1", [uid])
        if rows:
            return True
    if token:
        rows = _users_execute(
            "SELECT 1 AS ok FROM search_unlocks WHERE unlock_token=? LIMIT 1",
            [token],
        )
        if rows:
            return True
    return False


def _server_search_limit_reached(client_ip: str) -> bool:
    """Check if a free-tier IP has exceeded the daily server-side search limit."""
    if not client_ip or _SERVER_FREE_SEARCH_LIMIT <= 0:
        return False
    today = time.strftime("%Y-%m-%d")
    with _search_counter_lock:
        entry = _search_counters.get(client_ip)
        if not entry or entry["date"] != today:
            _search_counters[client_ip] = {"count": 1, "date": today}
            return False
        entry["count"] += 1
        return entry["count"] > _SERVER_FREE_SEARCH_LIMIT


def _is_oauth_verification_crawler_ua(user_agent: str) -> bool:
    """OAuth/policy crawlers must not hit the free-tier IP cap (429 can look like a login wall)."""
    ua = (user_agent or "").lower()
    if not ua:
        return False
    return any(
        t in ua
        for t in (
            "googlebot",
            "google-inspectiontool",
            "adsbot-google",
            "mediapartners-google",
            "apis-google",
            "bingbot",
            "slurp",
            "duckduckbot",
            "facebookexternalhit",
            "linkedinbot",
        )
    )


def _upsert_search_unlock(uid: int | None, token: str, source: str = "payment_return") -> str:
    token = (token or "").strip()
    if not token:
        raise ValueError("unlock token is required")
    rows = _users_execute(
        "SELECT id, user_id FROM search_unlocks WHERE unlock_token=? LIMIT 1",
        [token],
    )
    if rows:
        row_id = rows[0]["id"]
        row_uid = _session_user_id_int(rows[0].get("user_id"))
        if uid and row_uid != uid:
            _users_execute(
                "UPDATE search_unlocks SET user_id=?, source=?, last_seen=datetime('now') WHERE id=?",
                [uid, source, row_id],
            )
        else:
            _users_execute(
                "UPDATE search_unlocks SET source=?, last_seen=datetime('now') WHERE id=?",
                [source, row_id],
            )
        return token
    _users_execute(
        "INSERT INTO search_unlocks (user_id, unlock_token, source) VALUES (?,?,?)",
        [uid, token, source],
    )
    return token


def _get_user_by_id(uid: int) -> "dict | None":
    uid_i = _session_user_id_int(uid)
    if uid_i is None:
        return None
    rows = _users_execute("SELECT * FROM users WHERE id=?", [uid_i])
    return rows[0] if rows else None


def _get_user_by_login(identifier: str) -> "dict | None":
    ident = (identifier or "").strip()
    if not ident:
        return None
    rows = _users_execute(
        "SELECT * FROM users WHERE LOWER(email)=LOWER(?) OR LOWER(username)=LOWER(?)",
        [ident, ident],
    )
    return rows[0] if rows else None


def _user_is_email_verified(user: dict | None) -> bool:
    if not user:
        return False
    v = user.get("email_verified")
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    try:
        return int(v) != 0
    except (TypeError, ValueError):
        return bool(v)


def _random_otp6() -> str:
    return f"{secrets.randbelow(1000000):06d}"


def _otp_digest(user_id: int, code: str) -> str:
    raw = f"{int(user_id)}:{(code or '').strip()}"
    sk = (app.config.get("SECRET_KEY") or app.secret_key or "dev").encode("utf-8", errors="replace")
    return hmac.new(sk, raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _parse_db_ts(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        dt = val
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    s = str(val).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _ts_still_valid(val) -> bool:
    dt = _parse_db_ts(val)
    if not dt:
        return False
    return datetime.now(timezone.utc) <= dt


def _set_verification_challenge(user_id: int) -> tuple[str, str]:
    """Generate OTP + link token; persist hashes and expiry. Returns (otp_plain, verify_token)."""
    otp = _random_otp6()
    vtok = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    v_exp_s = (now + timedelta(hours=24)).isoformat()
    o_exp_s = (now + timedelta(minutes=15)).isoformat()
    otp_hash = _otp_digest(user_id, otp)
    _users_execute(
        "UPDATE users SET verify_token=?, verify_token_expires=?, otp_code_hash=?, otp_expires=? WHERE id=?",
        [vtok, v_exp_s, otp_hash, o_exp_s, user_id],
    )
    return otp, vtok


def _mark_email_verified(user_id: int) -> None:
    _users_execute(
        "UPDATE users SET email_verified=?, verify_token=NULL, verify_token_expires=NULL, "
        "otp_code_hash=NULL, otp_expires=NULL WHERE id=?",
        [True, user_id],
    )


def _send_signup_verification_email(
    to_email: str, username_display: str, otp: str, verify_token: str
) -> bool:
    base = _site_base_url().rstrip("/")
    q = urlencode({"token": verify_token})
    link = f"{base}/verify-email?{q}"
    subject = "Verify your abbiey.search account"
    text_body = (
        f"Hi {username_display},\n\n"
        f"Your verification code is: {otp}\n"
        f"(expires in 15 minutes)\n\n"
        f"Or open this link (expires in 24 hours):\n{link}\n\n"
        f"If you did not sign up, you can ignore this email.\n"
    )
    html_body = (
        f"<p>Hi {username_display},</p>"
        f"<p>Your verification code is:</p>"
        f'<p style="font-size:1.5rem;letter-spacing:0.2em;font-weight:bold">{otp}</p>'
        f'<p style="color:#666">Code expires in 15 minutes.</p>'
        f'<p>Or <a href="{link}">click here to verify your email</a> '
        f"(link expires in 24 hours).</p>"
        f'<p style="color:#666">If you did not create an account, you can ignore this message.</p>'
    )
    key = (os.environ.get("RESEND_API_KEY") or "").strip()
    from_addr = (os.environ.get("EMAIL_FROM") or "abbiey.search <onboarding@resend.dev>").strip()
    if not key:
        logger.warning(
            "RESEND_API_KEY not set — cannot send verification email to %s. OTP=%s URL=%s",
            to_email,
            otp,
            link,
        )
        return False
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "from": from_addr,
                "to": [to_email],
                "subject": subject,
                "text": text_body,
                "html": html_body,
            },
            timeout=20.0,
        )
        if r.status_code >= 400:
            logger.warning("Resend API error %s: %s", r.status_code, (r.text or "")[:500])
            return False
        return True
    except Exception as exc:
        logger.warning("Resend request failed: %s", exc)
        return False


@app.context_processor
def _inject_current_user():
    ctx = {
        "deploy_hash": DEPLOY_HASH,
        "google_site_verification": _GOOGLE_SITE_VERIFICATION,
        "google_analytics_id": _GOOGLE_ANALYTICS_ID,
        "site_base_url": _site_base_url(),
        "supabase_auth": _SUPABASE_AUTH_ENABLED,
        "supabase_url": _SUPABASE_URL if _SUPABASE_AUTH_ENABLED else "",
        "supabase_anon_key": _SUPABASE_ANON_KEY if _SUPABASE_AUTH_ENABLED else "",
        "csp_nonce": getattr(g, "csp_nonce", ""),
    }
    try:
        uid = _session_user_id_int(session.get("user_id"))
        if not uid:
            uid = _uid_from_sb_access_token_cookie()
        if not uid:
            return {**ctx, "current_user": None}
        user = _get_user_by_id(uid)
        if not user:
            return {**ctx, "current_user": None}
        if not _user_is_email_verified(user):
            session.pop("user_id", None)
            return {**ctx, "current_user": None}
        try:
            _users_execute(
                "UPDATE users SET last_seen=datetime('now') WHERE id=?", [uid]
            )
        except Exception:
            pass
        return {**ctx, "current_user": user}
    except Exception:
        logger.exception("inject_current_user_failed")
        return {**ctx, "current_user": None}


@app.after_request
def _response_policy_headers(resp):
    """HTML: avoid stale shells after deploy. APIs: CORS restricted to allowed origins."""
    try:
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "text/html" in ct:
            resp.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        if request.path.startswith("/api/"):
            _allowed_origins = {
                o.strip()
                for o in os.environ.get(
                    "CORS_ALLOWED_ORIGINS",
                    os.environ.get("SITE_URL", ""),
                ).split(",")
                if o.strip()
            }
            origin = request.headers.get("Origin", "")
            if origin and origin in _allowed_origins:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Vary"] = "Origin"
            resp.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            resp.headers.setdefault(
                "Access-Control-Allow-Headers",
                "Content-Type, X-Requested-With, Accept, Authorization",
            )
        return resp
    except Exception:
        logger.exception("_response_policy_headers_failed")
        return resp


@app.errorhandler(429)
def _handle_rate_limit(err):
    retry_after = getattr(err, "retry_after", None)
    payload = {"error": "rate_limited", "message": _RATE_LIMIT_MSG}
    if retry_after is not None:
        try:
            payload["retry_after"] = int(retry_after)
        except (TypeError, ValueError):
            pass
    if request.path.startswith("/api/"):
        return jsonify(payload), 429
    return (
        render_template(
            "error.html",
            code=429,
            title="Too Many Requests",
            message=_RATE_LIMIT_MSG,
            extra_help=False,
        ),
        429,
    )


@app.before_request
def _api_cors_preflight():
    if request.method != "OPTIONS" or not request.path.startswith("/api/"):
        return None
    return Response(
        "",
        status=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-Requested-With, Accept, Authorization",
            "Access-Control-Max-Age": "86400",
        },
    )


def _get_client_ip_from_request(req) -> str:
    """Best-effort client IP (honours X-Forwarded-For when behind a proxy)."""
    if req is None:
        return ""
    xf = (req.headers.get("X-Forwarded-For") or "").strip()
    if xf:
        return xf.split(",")[0].strip()[:80]
    rip = req.headers.get("X-Real-IP") or req.remote_addr or ""
    return (rip or "").strip()[:80]


def _is_public_ip(ip: str) -> bool:
    if not ip or ip.lower() in ("127.0.0.1", "::1", "unknown", "localhost"):
        return False
    if ip.startswith("10."):
        return False
    if ip.startswith("192.168."):
        return False
    if ip.startswith("169.254."):
        return False
    if ip.startswith("172."):
        parts = ip.split(".")
        if len(parts) >= 2:
            try:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return False
            except ValueError:
                pass
    if ip.startswith("fc") or ip.startswith("fd"):  # IPv6 ULA
        return False
    if ip == "::1":
        return False
    return True


def _summarize_user_agent(ua: str) -> str:
    ua = (ua or "")[:600]
    if not ua.strip():
        return "Unknown"
    l = ua.lower()
    if "ipad" in l or ("tablet" in l and "mobile" not in l):
        dev = "Tablet"
    elif "mobile" in l or "iphone" in l or "android" in l:
        dev = "Mobile"
    else:
        dev = "Desktop"
    br = "Browser"
    if "edg/" in l or "edga/" in l or "edgios/" in l:
        br = "Edge"
    elif "opr/" in l or "opera" in l:
        br = "Opera"
    elif "chrome" in l and "chromium" not in l:
        br = "Chrome"
    elif "firefox" in l:
        br = "Firefox"
    elif "safari" in l and "chrome" not in l:
        br = "Safari"
    elif "chromium" in l:
        br = "Chromium"
    return f"{dev} · {br}"


def _geo_lookup_ip(ip: str) -> str:
    """Resolve city/country via ip-api.com (free tier, no API key). Returns ''."""
    if not _is_public_ip(ip):
        return ""
    try:
        from urllib.parse import quote

        path_ip = quote(ip.strip(), safe="")
        r = httpx.get(
            f"https://ip-api.com/json/{path_ip}",
            params={"fields": "status,country,city"},
            timeout=2.5,
            headers={"User-Agent": "abbiey.search/1.0"},
        )
        data = r.json()
        if not data or data.get("status") != "success":
            return ""
        city = (data.get("city") or "").strip()
        country = (data.get("country") or "").strip()
        if city and country:
            return f"{city}, {country}"[:200]
        return (country or city)[:200]
    except Exception:
        return ""


def _insert_search_log_row(vals: list) -> "int | None":
    """Insert full search_logs row; return new id or None."""
    sql = (
        "INSERT INTO search_logs (query, search_type, region, result_count, latency_ms, hour, day_of_week,"
        " client_ip, user_agent, device_label, location) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    )
    if _SUPABASE_DB_URL and _SUPABASE_DB_READY:
        rows = _pg_execute(sql + " RETURNING id", vals)
        if rows and rows[0].get("id") is not None:
            return int(rows[0]["id"])
        return None
    if _LIBSQL_URL and _LIBSQL_TOKEN:
        rows = _turso_execute(sql + " RETURNING id", vals, db="analytics")
        if rows:
            rid = rows[0].get("id")
            if rid is not None:
                return int(rid)
        return None
    try:
        with sqlite3.connect(_ANALYTICS_DB) as con:
            cur = con.execute(sql, vals)
            con.commit()
            return int(cur.lastrowid) if cur.lastrowid else None
    except Exception:
        return None


def _analytics_query_digest(query: str) -> str:
    """Keyed digest for aggregate analytics without retaining raw query text."""
    q = (query or "").strip()
    if not q:
        return ""
    secret = str(app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY") or "abbiey-analytics")
    digest = hmac.new(
        secret.encode("utf-8", errors="replace"),
        q.encode("utf-8", errors="replace"),
        hashlib.sha256,
    ).hexdigest()
    return f"digest:{digest[:24]}"


# Bounded thread pool for async analytics — prevents thread explosion under load
_analytics_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="analytics")


def _log_search_worker(
    query: str,
    search_type: str,
    region: str,
    result_count: int,
    latency_ms: int,
    client_ip: str,
    user_agent: str,
    device_label: str,
    hour: int,
    day_of_week: int,
    ts: str,
):
    log = logging.getLogger(__name__)
    query_digest = _analytics_query_digest(query)
    vals = [
        query_digest,
        search_type,
        region or "",
        result_count,
        latency_ms,
        hour,
        day_of_week,
        (client_ip or "")[:80],
        (user_agent or "")[:512],
        (device_label or "")[:120],
        "",
    ]
    row_id = None
    try:
        row_id = _insert_search_log_row(vals)
    except Exception as exc:
        log.warning("Analytics insert failed: %s", exc)
    if row_id and client_ip and _is_public_ip(client_ip):
        loc = _geo_lookup_ip(client_ip)
        if loc:
            try:
                _analytics_execute(
                    "UPDATE search_logs SET location=? WHERE id=?",
                    [loc[:200], row_id],
                )
            except Exception:
                pass
    try:
        _sse_broadcast({
            "type": "search",
            "query": query_digest,
            "search_type": search_type,
            "results": result_count,
            "latency_ms": latency_ms,
            "ts": ts,
            "ip": (client_ip or "")[:80],
            "device": (device_label or "")[:80],
        })
    except Exception:
        pass


def _log_search(
    query: str,
    search_type: str,
    region: str,
    result_count: int,
    latency_ms: int = 0,
    request=None,
):
    """Async analytics log (bounded thread pool): query + client IP, UA, device, geo. Never blocks request."""
    import datetime as _dt

    now = _dt.datetime.now(_dt.timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    client_ip = _get_client_ip_from_request(request) if request else ""
    user_agent = ""
    if request:
        user_agent = (request.headers.get("User-Agent") or "")[:512]
    device_label = _summarize_user_agent(user_agent)
    args = (
        query,
        search_type,
        region,
        result_count,
        latency_ms,
        client_ip,
        user_agent,
        device_label,
        now.hour,
        now.weekday(),
        ts,
    )
    _analytics_pool.submit(_log_search_worker, *args)


def _log_error(route: str, message: str, level: str = "error"):
    """Log an error event to analytics DB — never raises."""
    try:
        _analytics_execute(
            "INSERT INTO error_logs (route, level, message) VALUES (?,?,?)",
            [route[:200], level, str(message)[:1000]],
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Query expansion — synonym dictionary
# ---------------------------------------------------------------------------
_SYNONYMS: "dict[str, list[str]]" = {
    "ai": ["artificial intelligence", "machine learning"],
    "ml": ["machine learning", "deep learning"],
    "js": ["javascript"],
    "ts": ["typescript"],
    "py": ["python"],
    "k8s": ["kubernetes"],
    "db": ["database"],
    "ui": ["user interface"],
    "ux": ["user experience"],
    "api": ["REST API", "web API"],
    "nlp": ["natural language processing"],
    "llm": ["large language model"],
    "gpt": ["large language model", "chatgpt"],
    "cli": ["command line", "terminal"],
    "vm": ["virtual machine"],
    "cdn": ["content delivery network"],
    "vpn": ["virtual private network"],
    "ssl": ["tls", "https encryption"],
    "docker": ["container", "containerization"],
    "ci": ["continuous integration", "devops"],
    "iot": ["internet of things"],
    "crypto": ["cryptocurrency", "blockchain"],
    "btc": ["bitcoin", "cryptocurrency"],
    "eth": ["ethereum"],
    "saas": ["software as a service"],
    "seo": ["search engine optimization"],
}


def _expand_query(query: str) -> "tuple[str, list[str]]":
    """
    Returns (expanded_query, added_terms).
    Appends OR-synonyms for known abbreviations — only for short queries
    to avoid over-broadening complex searches.
    """
    tokens = query.lower().split()
    if len(tokens) > 4:
        return query, []
    added: "list[str]" = []
    for token in tokens:
        clean = token.strip("\"'()[].,")
        if clean in _SYNONYMS:
            added.extend(_SYNONYMS[clean][:2])
    if not added:
        return query, []
    expansion = " OR ".join(f'"{s}"' for s in added[:3])
    return f"{query} {expansion}", added


@app.template_filter("domain")
def domain_filter(url):
    """Extract domain from URL for favicon lookups."""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

RESULTS_PER_PAGE = 20
MAX_PAGE = 50
MAX_QUERY_LENGTH = _max_query_length()
ALLOWED_TYPES = {"text", "images", "news", "videos", "code", "onion", "saved", "prices", "alts"}

# Price extraction
PRICE_RE = re.compile(
    r'(?:AU|NZ|CA?|HK|US)?\$\s*[\d,]+(?:\.\d{1,2})?'
    r'|(?:£|€|¥|₹|₩)\s*[\d,]+(?:\.\d{1,2})?'
    r'|[\d,]+(?:\.\d{1,2})?\s*(?:USD|GBP|EUR|AUD|CAD)\b',
    re.IGNORECASE,
)
RETAILER_DOMAINS = {
    "amazon.com": "Amazon", "amazon.co.uk": "Amazon", "amazon.com.au": "Amazon",
    "amazon.ca": "Amazon", "amazon.de": "Amazon",
    "ebay.com": "eBay", "ebay.co.uk": "eBay", "ebay.com.au": "eBay",
    "walmart.com": "Walmart",
    "bestbuy.com": "Best Buy",
    "target.com": "Target",
    "etsy.com": "Etsy",
    "newegg.com": "Newegg",
    "costco.com": "Costco",
    "bhphotovideo.com": "B&H Photo",
    "adorama.com": "Adorama",
    "officeworks.com.au": "Officeworks",
    "jbhifi.com.au": "JB Hi-Fi",
    "harveynorman.com.au": "Harvey Norman",
    "kogan.com": "Kogan",
    "aliexpress.com": "AliExpress",
    "pricespy.com.au": "PriceSpy",
    "staticice.com.au": "StaticICE",
    "getpricelist.com.au": "GetPrice",
    "shopping.google.com": "Google Shopping",
    "google.com": "Google Shopping",
}
CACHE_FETCH_SIZE = 100  # Fetch enough results to serve multiple pages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_MAX_PREVIEW_URL_LEN = 4096
_MAX_CHAT_HISTORY_TURNS = 12
_MAX_CHAT_MESSAGE_LEN = 12_000


def _log_event(event: str, **fields: object) -> None:
    """Structured log lines without embedding raw user search text."""
    parts = [event] + [f"{k}={v}" for k, v in sorted(fields.items()) if v is not None and v != ""]
    logger.info(" | ".join(parts))


@app.before_request
def _generate_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)


@app.after_request
def _security_headers(response):
    try:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        nonce = getattr(g, "csp_nonce", "")
        csp = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}' https://cdnjs.cloudflare.com "
            "https://www.googletagmanager.com https://www.google-analytics.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "img-src 'self' data: https: blob:; "
            "connect-src 'self' https: wss:; "
            "font-src 'self' data:; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        return response
    except Exception:
        logger.exception("_security_headers_failed")
        return response


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)
if ABBIEY_OPEN_ACCESS:
    limiter.enabled = False
    logging.getLogger(__name__).warning(
        "ABBIEY_OPEN_ACCESS is on: rate limiting disabled (intended for trusted self-hosts only)."
    )
# ---------------------------------------------------------------------------
# TTL cache for search results — fixes pagination instability
# ---------------------------------------------------------------------------
_cache = TTLCache(maxsize=1000, ttl=600)
_cache_lock = threading.Lock()
_in_flight: dict = {}
_in_flight_lock = threading.Lock()

# Onion link status cache (TTL 10 min)
_onion_status_cache = TTLCache(maxsize=2000, ttl=600)
_onion_status_lock = threading.Lock()

# Lazy-init shared httpx client
_http = None


def _get_http():
    global _http
    if _http is None:
        _http = httpx.Client(
            timeout=3.0,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=30),
        )
    return _http


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
def _wants_json_error_response() -> bool:
    """Prefer JSON error payloads for APIs and XHR (never raises)."""
    try:
        p = request.path or ""
        if p.startswith("/api/"):
            return True
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return True
        return request.accept_mimetypes.best == "application/json"
    except Exception:
        return False


def _safe_error_response(
    *,
    code: int,
    title: str,
    message: str,
    extra_help: bool = False,
    json_extras: dict | None = None,
):
    """
    Render error.html with fallbacks so template/include failures never produce a second crash.
    """
    if _wants_json_error_response():
        body = {
            "error": "server_error" if code >= 500 else "client_error",
            "code": code,
            "message": message,
        }
        if json_extras:
            body.update(json_extras)
        try:
            return jsonify(body), code
        except Exception:
            return Response(
                '{"error":"server_error","message":"Request could not be completed."}',
                status=code,
                mimetype="application/json",
            )
    try:
        return (
            render_template(
                "error.html",
                code=code,
                title=title,
                message=message,
                extra_help=extra_help,
                deploy_hash=DEPLOY_HASH,
            ),
            code,
        )
    except Exception:
        logger.exception("error_page_template_failed code=%s", code)
        msg = (
            str(message)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        ttl = str(title).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = (
            f'<!DOCTYPE html><html lang="en"><meta charset="utf-8"><title>{ttl}</title>'
            f'<body style="margin:2rem;font-family:system-ui;background:#0a0a0a;color:#eee">'
            f"<h1>{ttl}</h1><p>{msg}</p>"
            f'<p><a href="/search" style="color:#93c5fd">Back to search</a></p>'
            f'<p><a href="/api/access-resources" style="color:#93c5fd">Access resources (JSON)</a></p>'
            f"</body></html>"
        )
        return Response(html, status=code, mimetype="text/html; charset=utf-8")


@app.errorhandler(400)
def error_400(e):
    msg = "Invalid request."
    try:
        if getattr(e, "description", None):
            msg = str(e.description)
    except Exception:
        pass
    return _safe_error_response(code=400, title="Bad Request", message=msg)


@app.errorhandler(404)
def error_404(e):
    return _safe_error_response(
        code=404,
        title="Not Found",
        message="That path is not on this server. You can still search or use the access resources below.",
        extra_help=True,
    )
@app.errorhandler(429)
def error_429(e):
    if _wants_json_error_response():
        try:
            return (
                jsonify(
                    {
                        "error": "rate_limited",
                        "message": "Too many requests from this network. Wait briefly or use other tools listed in /api/access-resources.",
                        "resources": "/api/access-resources",
                    }
                ),
                429,
            )
        except Exception:
            return Response(
                '{"error":"rate_limited","resources":"/api/access-resources"}',
                status=429,
                mimetype="application/json",
            )
    return _safe_error_response(
        code=429,
        title="Too Many Requests",
        message=(
            "You hit a temporary limit so the service stays up for everyone. Wait a minute, try again, "
            "or use the links below — you are not out of options."
        ),
        extra_help=True,
    )
@app.errorhandler(500)
def error_500(e):
    return _safe_error_response(
        code=500,
        title="Server Error",
        message="Something failed on our side. Please retry; if it persists, use the open-web resources below.",
        extra_help=True,
    )
@app.errorhandler(Exception)
def error_unhandled_exception(exc):
    """Catch any unhandled error: log it, return HTML or JSON — never propagate to WSGI crash."""
    if isinstance(exc, HTTPException):
        return exc
    logger.exception("unhandled_exception %s %s", request.method, request.path)
    return _safe_error_response(
        code=500,
        title="Server Error",
        message="Something failed on our side. Please retry; if it persists, use the open-web resources below.",
        extra_help=True,
# ---------------------------------------------------------------------------
# Search operator parsing
# ---------------------------------------------------------------------------
    )
def _parse_operators(query):
    """Parse search operators from query.
    Returns (clean_query, operators_dict).
    Supported: site:, filetype:, before:, after:, lang:
    """
    operators = {}
    clean = query

    for op in ("site", "filetype", "before", "after", "lang"):
        pattern = re.compile(rf"\b{op}:(\S+)", re.IGNORECASE)
        matches = pattern.findall(clean)
        if matches:
            operators[op] = matches
            clean = pattern.sub("", clean)

    clean = re.sub(r"\s+", " ", clean).strip()
    return clean, operators


def _build_engine_query(clean_query, operators):
    """Rebuild query string with engine-supported operators."""
    parts = [clean_query]
    for key in ("site", "filetype", "before", "after"):
        for val in operators.get(key, []):
            parts.append(f"{key}:{val}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Dictionary lookup
# ---------------------------------------------------------------------------
_DEFINE_RE = re.compile(
    r"^(?:define\s+|definition\s+of\s+|what\s+is\s+(?:a\s+|an\s+|the\s+)?|meaning\s+of\s+)(.+?)$"
    r"|^(.+?)\s+(?:definition|meaning)$",
    re.IGNORECASE,
)
_QR_RE = re.compile(
    r"^(?:qr\s+code\s+for\s+|generate\s+qr\s+(?:code\s+)?(?:for\s+)?|qr\s+)(.+)$",
    re.IGNORECASE,
)
def _try_qr(query):
    """Detect QR code generation queries. Returns {data, image_url} or None."""
    m = _QR_RE.match(query.strip())
    if not m:
        return None
    data = m.group(1).strip()
    if not data or len(data) > 500:
        return None
    image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={quote_plus(data)}"
    return {"data": data, "image_url": image_url}


def _try_dictionary(query):
    """Check if query is a dictionary lookup and return word data if so."""
    m = _DEFINE_RE.match(query.strip())
    if not m:
        return None
    word = (m.group(1) or m.group(2) or "").strip()
    if not word or len(word) > 80:
        return None
    try:
        resp = httpx.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
            timeout=3.0,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None
        entry = data[0]
        phonetic = entry.get("phonetic", "")
        audio_url = ""
        for ph in entry.get("phonetics", []):
            if ph.get("audio"):
                audio_url = ph["audio"]
                if not phonetic and ph.get("text"):
                    phonetic = ph["text"]
                break
        definitions = []
        for meaning in entry.get("meanings", []):
            pos = meaning.get("partOfSpeech", "")
            for defn in meaning.get("definitions", [])[:2]:
                definitions.append({
                    "part_of_speech": pos,
                    "definition": defn.get("definition", ""),
                    "example": defn.get("example", ""),
                })
            if len(definitions) >= 3:
                break
        if not definitions:
            return None
        return {
            "word": entry.get("word", word),
            "phonetic": phonetic,
            "audio_url": audio_url,
            "definitions": definitions[:3],
        }
    except Exception:
        logger.warning("Dictionary lookup failed for word=%s", word)
        return None


# ---------------------------------------------------------------------------
# Calculator / math evaluation
# ---------------------------------------------------------------------------
import math as _math

_CALC_SAFE_GLOBALS = {"__builtins__": {}}
_CALC_SAFE_LOCALS = {
    "sqrt": _math.sqrt, "sin": _math.sin, "cos": _math.cos,
    "tan": _math.tan, "atan": _math.atan, "atan2": _math.atan2,
    "log": _math.log, "log10": _math.log10, "log2": _math.log2,
    "ln": _math.log, "abs": abs, "round": round,
    "ceil": _math.ceil, "floor": _math.floor,
    "pi": _math.pi, "e": _math.e, "tau": _math.tau,
    "pow": pow, "min": min, "max": max,
}
_CALC_KNOWN_NAMES = {"sqrt", "sin", "cos", "tan", "atan", "atan2", "log", "log10", "log2",
                     "ln", "abs", "round", "ceil", "floor", "pow", "pi", "e", "tau", "min", "max"}


def _try_calculator(query):
    """Evaluate math expressions safely. Returns {expression, result} or None."""
    import ast
    q = query.strip()
    if len(q) < 2 or len(q) > 200:
        return None
    # Must contain at least one digit or pi/e constant
    if not re.search(r"\d|(?<!\w)pi(?!\w)|(?<!\w)e(?!\w)", q):
        return None
    # Must contain at least one operator or function
    if not re.search(r"[+\-*/^()%]|sqrt|sin|cos|tan|log|ln|abs|round|ceil|floor|pow", q):
        return None
    # Sanitize: ^ to **, but keep % as modulo (Python native)
    expr = q.replace("^", "**")
    # Reject anything suspicious: only allow digits, operators, parens, spaces, dots, commas, and known function/constant names
    cleaned = re.sub(r"(sqrt|sin|cos|tan|atan2?|log10|log2|log|ln|abs|round|ceil|floor|pow|pi|tau|min|max)", "", expr)
    if re.search(r"[a-zA-Z_]", cleaned):
        return None
    # AST validation: parse and check all nodes are safe
    try:
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id not in _CALC_KNOWN_NAMES:
                return None
            if isinstance(node, ast.Attribute):
                return None  # No attribute access allowed
    except SyntaxError:
        return None
    try:
        import math
        result = eval(expr, _CALC_SAFE_GLOBALS, _CALC_SAFE_LOCALS)
        if isinstance(result, (int, float, complex)):
            if isinstance(result, float):
                if math.isinf(result) or math.isnan(result):
                    return {"expression": q, "result": str(result)}
                if result == int(result) and abs(result) < 1e15:
                    result = int(result)
                else:
                    result = round(result, 10)
            return {"expression": q, "result": str(result)}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Color picker detection + conversion
# ---------------------------------------------------------------------------
_HEX_COLOR_RE = re.compile(r"^#([0-9A-Fa-f]{3,8})$")
_RGB_COLOR_RE = re.compile(r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$", re.I)
_HSL_COLOR_RE = re.compile(r"^hsl\(\s*(\d{1,3})\s*,\s*(\d{1,3})%?\s*,\s*(\d{1,3})%?\s*\)$", re.I)


def _try_color_picker(query):
    """Detect color codes and convert between formats. Returns dict or None."""
    q = query.strip()
    r = g = b = None

    m = _HEX_COLOR_RE.match(q)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        elif len(h) == 6:
            pass
        else:
            return None
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    m = _RGB_COLOR_RE.match(q)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if any(v > 255 for v in (r, g, b)):
            return None

    m = _HSL_COLOR_RE.match(q)
    if m:
        h_val, s_val, l_val = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # HSL to RGB conversion
        s_f, l_f = s_val / 100, l_val / 100
        c = (1 - abs(2 * l_f - 1)) * s_f
        x = c * (1 - abs((h_val / 60) % 2 - 1))
        m_val = l_f - c / 2
        if h_val < 60:
            r1, g1, b1 = c, x, 0
        elif h_val < 120:
            r1, g1, b1 = x, c, 0
        elif h_val < 180:
            r1, g1, b1 = 0, c, x
        elif h_val < 240:
            r1, g1, b1 = 0, x, c
        elif h_val < 300:
            r1, g1, b1 = x, 0, c
        else:
            r1, g1, b1 = c, 0, x
        r, g, b = int((r1 + m_val) * 255), int((g1 + m_val) * 255), int((b1 + m_val) * 255)

    if r is None:
        return None

    # RGB to HEX
    hex_str = f"#{r:02x}{g:02x}{b:02x}"
    rgb_str = f"rgb({r}, {g}, {b})"

    # RGB to HSL
    r_f, g_f, b_f = r / 255, g / 255, b / 255
    c_max, c_min = max(r_f, g_f, b_f), min(r_f, g_f, b_f)
    delta = c_max - c_min
    l = (c_max + c_min) / 2
    if delta == 0:
        h, s = 0, 0
    else:
        s = delta / (1 - abs(2 * l - 1)) if (1 - abs(2 * l - 1)) != 0 else 0
        if c_max == r_f:
            h = 60 * (((g_f - b_f) / delta) % 6)
        elif c_max == g_f:
            h = 60 * (((b_f - r_f) / delta) + 2)
        else:
            h = 60 * (((r_f - g_f) / delta) + 4)
    hsl_str = f"hsl({int(h)}, {int(s * 100)}%, {int(l * 100)}%)"

    # Luminance for light/dark detection
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return {
        "hex": hex_str, "rgb_str": rgb_str, "hsl_str": hsl_str,
        "r": r, "g": g, "b": b, "is_light": luminance > 128,
    }


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------
_UNIT_RE = re.compile(
    r"^([\d.]+)\s*°?\s*([a-zA-Z\s°]+?)\s+(?:in|to)\s+°?\s*([a-zA-Z\s°]+?)$",
    re.I,
)
_UNIT_TABLE = {
    # Distance
    ("mi", "km"): lambda v: v * 1.60934, ("km", "mi"): lambda v: v / 1.60934,
    ("mi", "m"): lambda v: v * 1609.34, ("m", "mi"): lambda v: v / 1609.34,
    ("km", "m"): lambda v: v * 1000, ("m", "km"): lambda v: v / 1000,
    ("ft", "m"): lambda v: v * 0.3048, ("m", "ft"): lambda v: v / 0.3048,
    ("in", "cm"): lambda v: v * 2.54, ("cm", "in"): lambda v: v / 2.54,
    ("ft", "cm"): lambda v: v * 30.48, ("cm", "ft"): lambda v: v / 30.48,
    ("yd", "m"): lambda v: v * 0.9144, ("m", "yd"): lambda v: v / 0.9144,
    ("mi", "ft"): lambda v: v * 5280, ("ft", "mi"): lambda v: v / 5280,
    ("km", "ft"): lambda v: v * 3280.84, ("ft", "km"): lambda v: v / 3280.84,
    # Weight
    ("lb", "kg"): lambda v: v * 0.453592, ("kg", "lb"): lambda v: v / 0.453592,
    ("oz", "g"): lambda v: v * 28.3495, ("g", "oz"): lambda v: v / 28.3495,
    ("lb", "oz"): lambda v: v * 16, ("oz", "lb"): lambda v: v / 16,
    ("kg", "g"): lambda v: v * 1000, ("g", "kg"): lambda v: v / 1000,
    ("st", "kg"): lambda v: v * 6.35029, ("kg", "st"): lambda v: v / 6.35029,
    # Temperature
    ("f", "c"): lambda v: (v - 32) * 5 / 9, ("c", "f"): lambda v: v * 9 / 5 + 32,
    ("c", "k"): lambda v: v + 273.15, ("k", "c"): lambda v: v - 273.15,
    ("f", "k"): lambda v: (v - 32) * 5 / 9 + 273.15, ("k", "f"): lambda v: (v - 273.15) * 9 / 5 + 32,
    # Volume
    ("gal", "l"): lambda v: v * 3.78541, ("l", "gal"): lambda v: v / 3.78541,
    ("ml", "l"): lambda v: v / 1000, ("l", "ml"): lambda v: v * 1000,
    ("fl oz", "ml"): lambda v: v * 29.5735, ("ml", "fl oz"): lambda v: v / 29.5735,
    ("cup", "ml"): lambda v: v * 236.588, ("ml", "cup"): lambda v: v / 236.588,
    # Speed
    ("mph", "kph"): lambda v: v * 1.60934, ("kph", "mph"): lambda v: v / 1.60934,
    ("mph", "knots"): lambda v: v * 0.868976, ("knots", "mph"): lambda v: v / 0.868976,
    ("kph", "knots"): lambda v: v * 0.539957, ("knots", "kph"): lambda v: v / 0.539957,
    # Data
    ("mb", "gb"): lambda v: v / 1024, ("gb", "mb"): lambda v: v * 1024,
    ("gb", "tb"): lambda v: v / 1024, ("tb", "gb"): lambda v: v * 1024,
    ("kb", "mb"): lambda v: v / 1024, ("mb", "kb"): lambda v: v * 1024,
    ("kb", "gb"): lambda v: v / (1024 ** 2), ("gb", "kb"): lambda v: v * (1024 ** 2),
}

# Aliases for unit names
_UNIT_ALIASES = {
    "miles": "mi", "mile": "mi", "kilometers": "km", "kilometer": "km",
    "meters": "m", "meter": "m", "feet": "ft", "foot": "ft",
    "inches": "in", "inch": "in", "centimeters": "cm", "centimeter": "cm",
    "yards": "yd", "yard": "yd",
    "pounds": "lb", "pound": "lb", "lbs": "lb",
    "kilograms": "kg", "kilogram": "kg", "kgs": "kg",
    "ounces": "oz", "ounce": "oz",
    "grams": "g", "gram": "g", "stones": "st", "stone": "st",
    "fahrenheit": "f", "celsius": "c", "kelvin": "k",
    "gallons": "gal", "gallon": "gal", "liters": "l", "liter": "l", "litres": "l", "litre": "l",
    "milliliters": "ml", "milliliter": "ml", "cups": "cup",
    "knot": "knots",
    "megabytes": "mb", "gigabytes": "gb", "terabytes": "tb", "kilobytes": "kb",
}


def _try_unit_convert(query):
    """Parse and convert unit expressions. Returns dict or None."""
    m = _UNIT_RE.match(query.strip())
    if not m:
        return None
    try:
        value = float(m.group(1))
    except ValueError:
        return None
    from_raw = m.group(2).strip().lower()
    to_raw = m.group(3).strip().lower()
    from_unit = _UNIT_ALIASES.get(from_raw, from_raw)
    to_unit = _UNIT_ALIASES.get(to_raw, to_raw)
    converter = _UNIT_TABLE.get((from_unit, to_unit))
    if not converter:
        return None
    result = converter(value)
    # Format nicely
    if isinstance(result, float):
        result_formatted = f"{result:,.6g}"
    else:
        result_formatted = str(result)
    return {
        "value": m.group(1), "from_unit": from_raw,
        "to_unit": to_raw, "result": result,
        "result_formatted": result_formatted,
    }


# ---------------------------------------------------------------------------
# Knowledge panel (Wikipedia)
# ---------------------------------------------------------------------------
_ENTITY_HEURISTIC = re.compile(r"^[A-Za-z][A-Za-z\s\-\'\.]{1,60}$")


def _try_knowledge_panel(query):
    """Fetch Wikipedia summary + thumbnail for notable entities."""
    q = query.strip()
    # Heuristic: 1-4 words, looks like a noun/entity
    words = q.split()
    if len(words) < 1 or len(words) > 4:
        return None
    if not _ENTITY_HEURISTIC.match(q):
        return None
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": q,
                "prop": "extracts|pageimages",
                "piprop": "thumbnail",
                "pithumbsize": 300,
                "exintro": 1,
                "explaintext": 1,
                "exsentences": 4,
                "format": "json",
                "redirects": 1,
            },
            headers={"User-Agent": "abbiey.search/1.0 (privacy search engine)"},
            timeout=3.0,
        )
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid == "-1":
                return None
            extract = page.get("extract", "")
            if not extract or len(extract) < 50:
                return None
            image_url = page.get("thumbnail", {}).get("source", "")
            return {
                "title": page.get("title", q),
                "extract": extract,
                "image_url": image_url,
                "page_url": f"https://en.wikipedia.org/wiki/{quote_plus(page.get('title', q).replace(' ', '_'))}",
            }
    except Exception:
        _log_event("wikipedia_knowledge_panel_failed")
    return None


# ---------------------------------------------------------------------------
# Weather (Open-Meteo — free, no API key)
# ---------------------------------------------------------------------------
_WMO_EMOJI = {
    0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁️"), 45: ("Fog", "🌫️"), 48: ("Rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"), 53: ("Drizzle", "🌧️"), 55: ("Heavy drizzle", "🌧️"),
    61: ("Light rain", "🌦️"), 63: ("Rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
    71: ("Light snow", "🌨️"), 73: ("Snow", "❄️"), 75: ("Heavy snow", "❄️"),
    77: ("Snow grains", "❄️"), 80: ("Rain showers", "🌦️"), 81: ("Heavy showers", "🌧️"),
    82: ("Violent showers", "⛈️"), 85: ("Snow showers", "🌨️"), 86: ("Heavy snow showers", "🌨️"),
    95: ("Thunderstorm", "⛈️"), 96: ("Thunderstorm + hail", "⛈️"), 99: ("Thunderstorm + heavy hail", "⛈️"),
}


def _try_weather(location):
    """Fetch current weather + 3-day forecast for a location via Open-Meteo."""
    try:
        # Geocode
        geo = httpx.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en"},
            timeout=3.0,
        )
        geo_data = geo.json().get("results")
        if not geo_data:
            return None
        place = geo_data[0]
        lat, lon = place["latitude"], place["longitude"]
        loc_name = f"{place.get('name', location)}, {place.get('country', '')}"

        # Weather
        wx = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                "timezone": "auto",
                "forecast_days": 3,
            },
            timeout=3.0,
        )
        wx_data = wx.json()
        current = wx_data.get("current", {})
        daily = wx_data.get("daily", {})

        wmo_code = current.get("weather_code", 0)
        condition, emoji = _WMO_EMOJI.get(wmo_code, ("Unknown", "🌡️"))

        # Build 3-day forecast
        forecast = []
        times = daily.get("time", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        codes = daily.get("weather_code", [])
        from datetime import datetime
        for i in range(min(3, len(times))):
            day_name = datetime.strptime(times[i], "%Y-%m-%d").strftime("%a")
            fc_cond, fc_emoji = _WMO_EMOJI.get(codes[i] if i < len(codes) else 0, ("", "🌡️"))
            forecast.append({
                "day": day_name,
                "high": round(highs[i]) if i < len(highs) else "?",
                "low": round(lows[i]) if i < len(lows) else "?",
                "emoji": fc_emoji,
            })

        return {
            "location": loc_name,
            "temp": round(current.get("temperature_2m", 0)),
            "condition": condition,
            "emoji": emoji,
            "humidity": current.get("relative_humidity_2m", "?"),
            "wind": round(current.get("wind_speed_10m", 0)),
            "forecast": forecast,
        }
    except Exception:
        _log_event("weather_lookup_failed", backend="open_meteo")
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
_TEMPLATE_DEFAULTS = dict(
    query="", results=[], search_type="text", has_more=False, page=1,
    entities=[], primary_entity=None, entity_results=[], operators={},
    region="", lang="", dictionary=None, calculator=None, color=None,
    unit_convert=None, knowledge=None, weather=None, qr=None, time_filter="",
    image_search_advanced=False,
    img_ov_license="",
    img_ov_license_type="",
    img_ov_aspect="",
    img_ov_size="",
    img_ov_ext="",
    img_ov_src="",
    img_src_checked=["ddg", "openverse", "commons"],
    img_scroll_extras="",
    query_ui={
        "intent": "informational",
        "interrogative_or_explanatory": False,
        "local_intent": False,
        "transactional_local_keywords": False,
        "prefer_local_ui": False,
        "show_ai_summary": False,
        "clarify": None,
        "answer_mode": "standard",
    },
    search_lat=None,
    search_lon=None,
    show_ai_summary_block=False,
    show_answer_layer_block=False,
    search_notice=None,
    current_user_has_paid_access=False,
    stripe_search_checkout_url=STRIPE_SEARCH_CHECKOUT_URL,
    cleanweb=False,
    safeguard={"show_crisis_strip": False, "show_inclusive_hint": False, "chaotic_query": False},
    osint_enabled=True,
)
def should_show_ai_summary(query: str, intent: str) -> bool:
    """Gate AI summary card + /api/ai-summary: block obvious local/transactional queries."""
    q = (query or "").lower()
    hard_block = [
        "near me",
        "closest",
        "open now",
        "directions",
        "distance",
        "map",
    ]
    if any(x in q for x in hard_block):
        return False
    # App uses local_search; include "local" for callers that pass a short label.
    if intent in ("transactional", "local", "local_search"):
        return False
    return True


@app.route("/")
def index():
    """First visit: onboarding at /welcome. Returning visitors and signed-in users: /search."""
    if os.environ.get("ABBIEY_SKIP_WELCOME_SCREEN") == "1":
        return redirect(url_for("search"), code=301)
    if _session_user_id_int(session.get("user_id")):
        return redirect(url_for("search"), code=301)
    if (request.cookies.get(_WELCOME_COOKIE) or "").strip() == "1":
        return redirect(url_for("search"), code=301)
    return redirect(url_for("welcome"), code=302)


@app.route("/welcome")
def welcome():
    """First-visit signup walkthrough (Google OAuth + optional phone). Direct URL always works; root / uses env + cookie."""
    if _session_user_id_int(session.get("user_id")):
        return redirect(url_for("search"))
    if (request.cookies.get(_WELCOME_COOKIE) or "").strip() == "1":
        return redirect(url_for("search"))
    return render_template(
        "welcome.html",
        supabase_url=_SUPABASE_URL,
        supabase_anon_key=_SUPABASE_ANON_KEY,
        supabase_auth=_SUPABASE_AUTH_ENABLED,
    )


@app.route("/welcome/dismiss")
def welcome_dismiss():
    """Skip onboarding and use search without an account."""
    resp = redirect(url_for("search"))
    _set_welcome_seen_cookie(resp)
    return resp


@app.route("/about")
def about():
    """About page for product positioning and search approach."""
    return render_template("about.html")


@app.route("/landing")
def landing():
    """Backward-compatible redirect for the old about URL."""
    return redirect(url_for("about"), code=301)


@app.route("/privacy")
def privacy():
    """Privacy policy page."""
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    """Terms of service page."""
    return render_template("terms.html")


@app.route("/payment-return")
def payment_return():
    """Stripe Payment Link redirect target: sends users back to search (with unlock) or /developer."""
    return render_template("payment_return.html")


@app.route("/api/search-access", methods=["GET"])
def api_search_access():
    uid = _session_user_id_int(session.get("user_id"))
    cookie_token = _search_unlock_cookie_token()
    account_token = _search_access_token_for_user(uid)
    unlocked = False
    source = "none"
    token_to_set = cookie_token or account_token

    if uid and account_token:
        unlocked = True
        source = "account"
        if cookie_token:
            try:
                _upsert_search_unlock(uid, cookie_token, source="session_link")
                token_to_set = cookie_token
            except Exception:
                logger.exception("search_access_session_link_failed")
        elif account_token:
            token_to_set = account_token
    elif cookie_token and _search_access_granted(token=cookie_token):
        unlocked = True
        source = "browser"
        if uid:
            try:
                _upsert_search_unlock(uid, cookie_token, source="session_link")
            except Exception:
                logger.exception("search_access_cookie_link_failed")
    elif uid and _search_access_granted(uid=uid):
        unlocked = True
        source = "account"
        token_to_set = account_token

    resp = jsonify({"unlocked": unlocked, "source": source})
    if unlocked and token_to_set:
        _set_search_unlock_cookie(resp, token_to_set)
    return resp


@app.route("/api/search-access/prepare-checkout", methods=["POST"])
@limiter.limit("30/minute")
def api_search_access_prepare_checkout():
    ts_str = str(time.time())
    session[_SEARCH_CHECKOUT_PENDING_SESSION_KEY] = ts_str
    sig = hmac.new(
        _checkout_hmac_key(), ts_str.encode(), hashlib.sha256
    ).hexdigest()[:16]
    # Generate a checkout reference token so Stripe webhook can link payment to user
    checkout_token = secrets.token_urlsafe(24)
    uid = _session_user_id_int(session.get("user_id"))
    client_ip = request.remote_addr or ""
    try:
        _users_execute(
            "INSERT INTO pending_checkouts (checkout_token, user_id, client_ip) VALUES (?,?,?)",
            [checkout_token, uid, client_ip],
        )
    except Exception:
        logger.exception("pending_checkout_insert_failed")
    resp = jsonify({"ok": True, "checkout_token": checkout_token, "checkout_url": STRIPE_SEARCH_CHECKOUT_URL})
    resp.set_cookie(
        _SEARCH_CHECKOUT_PENDING_COOKIE,
        f"{ts_str}.{sig}",
        max_age=_SEARCH_CHECKOUT_PENDING_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=app.config.get("SESSION_COOKIE_SECURE", False),
    )
    return resp


@app.route("/api/search-access/claim", methods=["POST"])
@limiter.limit("30/minute")
def api_search_access_claim():
    checkout_token = (request.json or {}).get("checkout_token", "") if request.is_json else ""
    # Check if this payment was already verified by Stripe webhook
    webhook_verified = False
    if checkout_token:
        try:
            rows = _users_execute(
                "SELECT 1 AS ok FROM payment_events WHERE checkout_token=? LIMIT 1",
                [checkout_token],
            webhook_verified = bool(rows)
            )
        except Exception:
            pass
    if not webhook_verified and not _search_checkout_pending():
        return jsonify({"error": "checkout_not_pending", "message": "Checkout could not be verified."}), 409
    uid = _session_user_id_int(session.get("user_id"))
    token = _search_unlock_cookie_token() or secrets.token_urlsafe(32)
    try:
        token = _upsert_search_unlock(uid, token, source="webhook_verified" if webhook_verified else "payment_return")
    except Exception:
        logger.exception("search_access_claim_failed")
        return jsonify({"error": "unavailable", "message": "Unlimited access could not be restored right now."}), 503
    # Mark the pending checkout as claimed
    if checkout_token:
        try:
            _users_execute(
                "UPDATE pending_checkouts SET status='claimed' WHERE checkout_token=?",
                [checkout_token],
            )
        except Exception:
            pass
    session.pop(_SEARCH_CHECKOUT_PENDING_SESSION_KEY, None)
    resp = jsonify({"ok": True, "unlocked": True, "source": "account" if uid else "browser"})
    _set_search_unlock_cookie(resp, token)
    resp.delete_cookie(_SEARCH_CHECKOUT_PENDING_COOKIE)
    return resp


_RESTORE_BY_EMAIL_PUBLIC_MESSAGE = (
    "If this email is associated with a purchase, unlimited search is enabled in this browser. "
    "Otherwise, nothing has changed — you can keep using the site as usual."
)
def _email_acceptable_for_restore(raw: str) -> bool:
    s = (raw or "").strip()
    if len(s) < 3 or len(s) > 254 or s.count("@") != 1:
        return False
    local, domain = s.split("@", 1)
    if not local or not domain or "." not in domain:
        return False
    if ".." in local or ".." in domain or local.startswith(".") or domain.startswith("."):
        return False
    return True


@app.route("/api/search-access/restore-by-email", methods=["POST"])
@limiter.limit("20/minute")
def api_search_access_restore_by_email():
    """Re-issue an unlock cookie when the email matches a recorded Stripe payment.

    Returns HTTP 200 with the same JSON body whether or not a payment exists, so clients cannot
    infer paid-vs-unknown from status codes (enumeration resistance). Only successful payment
    lookups also set the HttpOnly unlock cookie.
    """
    if not request.is_json:
        return jsonify({"ok": False, "error": "expected_json"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "invalid_body"}), 400
    raw_email = (body.get("email") or "").strip()
    if not raw_email:
        return jsonify({"ok": False, "error": "email_required"}), 400
    if not _email_acceptable_for_restore(raw_email):
        return jsonify({"ok": False, "error": "invalid_email"}), 400

    email_norm = raw_email.lower().strip()
    paid_rows: list = []
    try:
        paid_rows = _users_execute(
            "SELECT 1 AS ok FROM payment_events WHERE LOWER(TRIM(COALESCE(customer_email, ''))) = ? LIMIT 1",
            [email_norm],
        )
    except Exception:
        logger.exception("restore_by_email: payment_events lookup failed")
        return jsonify({"ok": False, "error": "unavailable"}), 503

    payload = {"ok": True, "message": _RESTORE_BY_EMAIL_PUBLIC_MESSAGE}
    resp = jsonify(payload)

    if not paid_rows:
        return resp, 200

    uid: int | None = None
    try:
        urows = _users_execute(
            "SELECT id FROM users WHERE LOWER(email) = ? LIMIT 1",
            [email_norm],
        )
        if urows:
            uid = _session_user_id_int(urows[0].get("id"))
    except Exception:
        logger.exception("restore_by_email: users lookup failed")

    try:
        token = secrets.token_urlsafe(32)
        token = _upsert_search_unlock(uid, token, source="restore_by_email")
        _set_search_unlock_cookie(resp, token)
    except Exception:
        logger.exception("restore_by_email: grant failed")
        return jsonify({"ok": False, "error": "unavailable"}), 503

    return resp, 200


# ---------------------------------------------------------------------------
# Stripe Webhook — server-side payment verification
# ---------------------------------------------------------------------------
@app.route("/webhooks/stripe", methods=["POST"])
@limiter.exempt
def stripe_webhook():
    """Verify Stripe webhook signature and auto-grant access on successful payment."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("stripe_webhook: STRIPE_WEBHOOK_SECRET not set — ignoring webhook")
        return jsonify({"received": True}), 200

    if not _stripe_mod:
        logger.error("stripe_webhook: stripe package not installed")
        return jsonify({"error": "stripe not available"}), 500

    try:
        event = _stripe_mod.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError:
        logger.warning("stripe_webhook: invalid payload")
        return jsonify({"error": "invalid payload"}), 400
    except _stripe_mod.error.SignatureVerificationError:
        logger.warning("stripe_webhook: invalid signature")
        return jsonify({"error": "invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        checkout_token = sess.get("client_reference_id", "")
        customer_email = sess.get("customer_details", {}).get("email", "") or sess.get("customer_email", "")
        amount = sess.get("amount_total", 0)
        currency = sess.get("currency", "usd")
        stripe_session_id = sess.get("id", "")
        stripe_event_id = event.get("id", "")

        # Record the payment event (idempotent via UNIQUE stripe_event_id)
        try:
            _users_execute(
                "INSERT INTO payment_events (stripe_event_id, stripe_session_id, checkout_token, customer_email, amount_cents, currency) "
                "VALUES (?,?,?,?,?,?)",
                [stripe_event_id, stripe_session_id, checkout_token, customer_email, amount, currency],
            )
        except Exception:
            logger.info("stripe_webhook: payment_event already recorded (event_id=%s)", stripe_event_id)

        # Auto-grant search unlock if checkout_token links to a pending checkout.
        # Uses a single atomic UPDATE to avoid double-grant on Stripe webhook retries.
        if checkout_token:
            try:
                rows = _users_execute(
                    "UPDATE pending_checkouts SET status='webhook_verified' "
                    "WHERE checkout_token=? AND status='pending' RETURNING user_id",
                    [checkout_token],
                )
                if rows:
                    uid = _session_user_id_int(rows[0].get("user_id"))
                    token = secrets.token_urlsafe(32)
                    _upsert_search_unlock(uid, token, source="stripe_webhook")
                    logger.info("stripe_webhook: auto-granted access for checkout_token=%s", checkout_token[:8])
            except Exception:
                logger.exception("stripe_webhook: auto-grant failed for checkout_token=%s", checkout_token[:8] if checkout_token else "?")

        # Email-based fallback: no checkout_token (direct Payment Link, no pre-created session).
        # Look up the paying user by email and grant access.
        elif customer_email:
            try:
                users = _users_execute(
                    "SELECT id FROM users WHERE LOWER(email)=LOWER(?)",
                    [customer_email],
                )
                if users:
                    uid = _session_user_id_int(users[0].get("id"))
                    token = secrets.token_urlsafe(32)
                    _upsert_search_unlock(uid, token, source="stripe_webhook_email")
                    logger.info("stripe_webhook: email-based auto-grant for email=%s", customer_email[:20])
            except Exception:
                logger.exception("stripe_webhook: email-based auto-grant failed")

    return jsonify({"received": True}), 200


ACCESS_RESOURCES_JSON = {
    "about": (
        "abbiey.search is built so a single outage or limit does not leave you with nowhere to go. "
        "We stack multiple engines, publish open JSON helpers, and allow generous limits so research "
        "and access are not artificially cramped."
    ),
    "this_site": {
        "search": "/search",
        "deep_web_tab": "/search?type=onion",
        "access_json": "/api/access-resources",
    },
    "privacy_tools": {
        "tor_browser": "https://www.torproject.org/download/",
        "ahmia_clearnet_index": "https://ahmia.fi",
        "internet_archive": "https://web.archive.org",
        "marginalia_search": "https://search.marginalia.nu",
        "searx_public_directory": "https://searx.space",
    },
    "tips": [
        "If one tab (e.g. News) is empty, try All or Web — backends differ.",
        "For .onion sites, use Tor Browser; Ahmia on the Deep Web tab works from the clearnet.",
        "Long queries are allowed (see ABBIEY_MAX_QUERY_LENGTH) for power users and pasted context.",
    ],
}


@app.route("/api/access-resources")
@limiter.exempt
def api_access_resources():
    """Always-available JSON: mirrors, Tor, and archives so users are never philosophically 'stuck'."""
    return jsonify(ACCESS_RESOURCES_JSON)


def _parse_request_coord(name):
    """Parse float query param (lat/lon); empty or invalid → None."""
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _reverse_geocode_label(lat, lon):
    """City/town label for local query injection (Nominatim reverse)."""
    try:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": "abbiey.search/1.0"},
            timeout=2.0,
        )
        data = resp.json()
        addr = data.get("address") or {}
        for key in ("city", "town", "village", "municipality", "state"):
            if addr.get(key):
                return str(addr[key]).strip()
        disp = (data.get("display_name") or "").strip()
        return disp.split(",")[0].strip() if disp else None
    except Exception:
        logger.debug("reverse_geocode_failed", exc_info=True)
        return None


_LOCAL_MAPS_HOST_RE = re.compile(
    r"(google\.com/maps|maps\.google|goo\.gl/maps|openstreetmap\.org|yelp\.|tripadvisor\.|"
    r"foursquare\.|yellowpages|bing\.com/maps|mapquest\.|here\.com)",
    re.I,
)
def _local_probe_score(result, loc_ctx):
    """Proxy score when true distance per snippet is unavailable (DDG has no lat/lon per hit)."""
    url = (result.get("url") or "").lower()
    title = (result.get("title") or "").lower()
    body = (result.get("body") or "").lower()
    blob = f"{title} {body} {url}"
    domain_boost = 1.0 if _LOCAL_MAPS_HOST_RE.search(url) else 0.35
    anchor = (loc_ctx.get("anchor_label") or loc_ctx.get("location_from_query") or "").lower()
    anchor_tokens = [t for t in re.split(r"\W+", anchor) if len(t) > 2]
    overlap = 0.0
    if anchor_tokens:
        hits = sum(1 for t in anchor_tokens if t in blob)
        overlap = min(1.0, hits / max(len(anchor_tokens), 1))
    rating_eg = (
        1.0 if re.search(r"\b\d\.\d\s*★|⭐|\bout of 5\b|\bstars?\b", blob) else 0.0
    )
    engagement = min(1.0, len(body) / 380.0)
    return 0.65 * domain_boost + 0.25 * overlap + 0.10 * (0.7 * rating_eg + 0.3 * engagement)


def _rank_local_search_results(results, loc_ctx):
    if not results or not loc_ctx or not loc_ctx.get("has_local_intent"):
        return results
    scored = list(enumerate(results))
    scored.sort(key=lambda ix: (-_local_probe_score(ix[1], loc_ctx), ix[0]))
    return [r for _, r in scored]


# Heuristic re-ranking: demote common SEO listicle / affiliate patterns; boost substantive snippets
# and spread domains. Best-effort only — skips when local intent ranking already ran.
_LISTICLE_HEADLINE_RE = re.compile(
    r"(?i)(^|\s)(best|top)\s*\d+|\d+\s+(best|top|ways|tips|reasons|things)\b|"
    r"ultimate\s+guide|buyers?\s+guide|buying\s+guide|"
    r"(roundup|ranked|we\s+tested|products?\s+you)\b|"
    r"#\d+\s|^\d+[\.)]\s",
)
_AFFILIATE_SNIPPET_RE = re.compile(
    r"(?i)affiliate|commission|sponsored\s+post|paid\s+link|amazon\s+associate|"
    r"advertiser\s+disclosure|this\s+post\s+contains\s+affiliate",
)
_VS_SPAM_RE = re.compile(r"(?i)\bvs\.?\b.*\bvs\.?\b")


def _host_key_for_diversity(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _anti_template_base_score(result: dict) -> float:
    title = (result.get("title") or "")[:220]
    body = (result.get("body") or result.get("description") or "")[:600]
    blob = f"{title} {body}".strip()
    title_l = title.lower()
    blob_l = blob.lower()
    score = 0.0
    blen = len(body.strip())
    if blen >= 160:
        score += 0.38
    elif blen >= 85:
        score += 0.2
    elif blen > 0 and blen < 38:
        score -= 0.22

    if _LISTICLE_HEADLINE_RE.search(title_l) or _LISTICLE_HEADLINE_RE.search(blob_l):
        score -= 0.52
    if _VS_SPAM_RE.search(title_l):
        score -= 0.35
    if _AFFILIATE_SNIPPET_RE.search(blob_l):
        score -= 0.65

    st = (result.get("source_type") or "").lower()
    if st == "academic":
        score += 0.42
    src_l = (result.get("source") or "").lower()
    for needle in ("marginalia", "wikipedia", "arxiv", "pubmed", "crossref", "internet archive"):
        if needle in src_l:
            score += 0.22
            break

    date_s = (result.get("date") or "")[:32]
    if re.search(r"202[4-9]", date_s):
        score += 0.06
    elif re.search(r"201[0-9]", date_s) and not re.search(r"202[0-9]", title_l):
        score -= 0.05

    return score


def _rank_anti_template_results(results: list) -> list:
    """Re-order text hits to surface more original / substantive pages (optional user mode)."""
    if not results or len(results) < 2:
        return results
    n = len(results)
    keys = [_host_key_for_diversity(r.get("url") or "") for r in results]
    host_freq = Counter(k for k in keys if k)
    base = [_anti_template_base_score(r) for r in results]
    domain_counts: dict[str, int] = {}
    adjusted = []
    for i in range(n):
        key = keys[i]
        prior = domain_counts.get(key, 0) if key else 0
        if key:
            domain_counts[key] = prior + 1
        dup_penalty = 0.14 * prior if key else 0.0
        solo_bonus = 0.12 if key and host_freq.get(key, 0) == 1 else 0.0
        adjusted.append(base[i] - dup_penalty + solo_bonus)
    order = sorted(range(n), key=lambda i: (-adjusted[i], i))
    return [results[i] for i in order]


@app.route("/search")
@limiter.limit("120/minute")
def search():
    query = request.args.get("q", "").strip()
    page = max(1, min(request.args.get("page", 1, type=int), MAX_PAGE))
    search_type = request.args.get("type", "text")
    region = request.args.get("region", "").strip() or None
    lang = request.args.get("lang", "").strip() or None
    time_filter = request.args.get("df", "").strip()
    if time_filter not in {"d", "w", "m", "y"}:
        time_filter = ""
    safesearch = request.args.get("safesearch", "off").strip()
    if safesearch not in {"off", "moderate", "strict"}:
        safesearch = "off"

    current_uid = _session_user_id_int(session.get("user_id"))
    current_user_has_paid_access = _search_access_granted(
        uid=current_uid, token=_search_unlock_cookie_token()
    )
    if search_type not in ALLOWED_TYPES:
        search_type = "text"

    cleanweb = request.args.get("cleanweb", "").strip().lower() in ("1", "true", "yes", "on")
    anti_template = bool(cleanweb and search_type == "text")

    image_opts = _parse_image_search_options() if search_type == "images" else None

    # Feature gate enforcement — blocks gated search types early
    _type_to_gate = {"onion": "deep_web", "code": "code_search"}
    _gate_name = _type_to_gate.get(search_type)
    if _gate_name:
        if not _feature_allowed(_gate_name, unlocked=current_user_has_paid_access):
            # "none" gate → 404 (feature disabled); "paid" gate for free user → 403
            gate_val = _FEATURE_GATES.get(_gate_name, "all")
            if gate_val == "none":
                return render_template("error.html", code=404, title="Feature Unavailable",
                                       message="This search type is not available.", extra_help=False), 404
            return render_template("error.html", code=403, title="Paid Feature",
                                   message="This search type requires a paid account.", extra_help=False), 403

    user_feature_gates = _feature_gates_for_user(current_user_has_paid_access)

    if not query:
        return render_template(
            "index.html",
            **{
                **_TEMPLATE_DEFAULTS,
                "current_user_has_paid_access": current_user_has_paid_access,
                "osint_enabled": _abbiey_osint_enabled(),
            },
    # Server-side search limit for free-tier users
        )
    if query and not current_user_has_paid_access:
        client_ip = request.remote_addr or ""
        ua = request.headers.get("User-Agent") or ""
        if not _is_oauth_verification_crawler_ua(ua) and _server_search_limit_reached(client_ip):
            return render_template(
                "index.html",
                **{
                    **_TEMPLATE_DEFAULTS,
                    "current_user_has_paid_access": False,
                    "osint_enabled": _abbiey_osint_enabled(),
                    "search_notice": "You\u2019ve reached your daily free search limit. Unlock unlimited searches or wait 24 hours.",
                },
            ), 429

    if search_type == "saved":
        return render_template(
            "index.html",
            query=query,
            results=[],
            search_type="saved",
            has_more=False,
            page=1,
            entities=[],
            primary_entity=None,
            entity_results=[],
            operators={},
            region=region or "",
            lang=lang or "",
            dictionary=None,
            calculator=None,
            color=None,
            unit_convert=None,
            knowledge=None,
            weather=None,
            qr=None,
            time_filter="",
            image_search_advanced=False,
            img_ov_license="",
            img_ov_license_type="",
            img_ov_aspect="",
            img_ov_size="",
            img_ov_ext="",
            img_ov_src="",
            img_src_checked=[],
            img_scroll_extras="",
            query_ui=_TEMPLATE_DEFAULTS["query_ui"],
            search_lat=None,
            search_lon=None,
            show_ai_summary_block=False,
            show_answer_layer_block=False,
            search_notice=None,
            current_user_has_paid_access=current_user_has_paid_access,
            cleanweb=False,
            safeguard={"show_crisis_strip": False, "show_inclusive_hint": False, "chaotic_query": False},
            osint_enabled=_abbiey_osint_enabled(),
        )
    if len(query) > MAX_QUERY_LENGTH:
        return render_template(
            "error.html", code=400, title="Query Too Long",
            message=(
                f"This query exceeds the current limit ({MAX_QUERY_LENGTH} characters). "
                "Shorten it, split into two searches, or self-host with a higher ABBIEY_MAX_QUERY_LENGTH."
            ),
            extra_help=True,
        ), 400

    # Parse search operators
    clean_query, operators = _parse_operators(query)
    if operators.get("lang"):
        lang = operators["lang"][0]

    # Query expansion
    expanded_query, expansion_terms = _expand_query(clean_query)
    if expansion_terms:
        clean_query = expanded_query

    user_lat = _parse_request_coord("lat")
    user_lon = _parse_request_coord("lon")
    if user_lat is not None and not (-90 <= user_lat <= 90):
        user_lat = None
    if user_lon is not None and not (-180 <= user_lon <= 180):
        user_lon = None

    prep = preprocess_query(clean_query)
    query_ui = query_ui_hints(prep)
    anchor_geo = None
    if user_lat is not None and user_lon is not None and has_local_intent_signals(prep):
        anchor_geo = _reverse_geocode_label(user_lat, user_lon)
    loc_ctx = resolve_location_for_search(prep, user_lat, user_lon, anchor_geo)
    backend_query = build_backend_search_query(clean_query, prep, loc_ctx)
    local_rank_context = loc_ctx if search_type == "text" and loc_ctx.get("has_local_intent") else None

    # Entity detection
    entities = detect_entities(query)
    primary = primary_entity(entities)
    entity_queries = build_search_queries(query, entities) if entities else []

    # Geocode address entities that lack lat/lon
    if primary and primary.type == "address" and not primary.meta.get("lat"):
        try:
            geo_resp = httpx.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": primary.normalized, "format": "json", "limit": "1"},
                headers={"User-Agent": "abbiey.search/1.0"},
                timeout=3.0,
            )
            geo_data = geo_resp.json()
            if geo_data and isinstance(geo_data, list) and geo_data[0].get("lat"):
                primary.meta["lat"] = float(geo_data[0]["lat"])
                primary.meta["lon"] = float(geo_data[0]["lon"])
        except Exception:
            logger.warning("Nominatim geocoding failed for address=%s", primary.normalized)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        _t_ajax = time.perf_counter()
        results = _fetch_results(
            backend_query,
            page,
            search_type,
            region,
            lang,
            operators,
            time_filter=time_filter,
            safesearch=safesearch,
            image_opts=image_opts,
            local_rank_context=local_rank_context,
            anti_template=anti_template,
            source_query_for_fallback=query,
        )
        _ajax_ms = int((time.perf_counter() - _t_ajax) * 1000)
        if page == 1:
            _log_search(query, search_type, region or "", len(results.get("results", [])), _ajax_ms, request=request)
            if current_uid and query and search_type != "saved":
                try:
                    _pet_try_award(current_uid, "search")
                except Exception:
                    pass
        return jsonify(results)

    _t0 = time.perf_counter()
    results = _fetch_results(
        backend_query,
        1,
        search_type,
        region,
        lang,
        operators,
        time_filter=time_filter,
        safesearch=safesearch,
        image_opts=image_opts,
        local_rank_context=local_rank_context,
        anti_template=anti_template,
        source_query_for_fallback=query,
    )
    _latency_ms = int((time.perf_counter() - _t0) * 1000)

    # Log search analytics (non-blocking, never fails)
    if page == 1:
        _log_search(query, search_type, region or "", len(results.get("results", [])), _latency_ms, request=request)
        if current_uid and query and search_type != "saved":
            try:
                _pet_try_award(current_uid, "search")
            except Exception:
                pass

    # Fetch entity-specific results on page 1 (text only) — parallel
    entity_results = []
    entity_urls = set()
    if entities and search_type == "text" and page == 1:
        _eq_slice = entity_queries[:4]
        with ThreadPoolExecutor(max_workers=4) as _eq_pool:
            _eq_futures = {
                _eq_pool.submit(_fetch_results, eq["query"], 1, eq["type"]): eq
                for eq in _eq_slice
            }
            for fut in as_completed(_eq_futures):
                eq = _eq_futures[fut]
                try:
                    er = fut.result(timeout=6)
                except Exception:
                    continue
                if er["results"]:
                    for r in er["results"][:3]:
                        entity_urls.add(r.get("url", ""))
                    entity_results.append({
                        "label": eq["label"],
                        "results": er["results"][:3],
                    })

    # Deduplicate: remove entity result URLs from main results
    if entity_urls:
        results["results"] = [r for r in results["results"] if r.get("url", "") not in entity_urls]

    # Dictionary card (text tab, page 1 only)
    dictionary = None
    qr = None
    calculator = None
    color = None
    unit_convert = None
    knowledge = None
    weather = None
    if search_type == "text" and page == 1:
        dictionary = _try_dictionary(query)
        qr = _try_qr(query)
        # Color picker (before entity detection so #hex doesn't become hashtag)
        color = _try_color_picker(query)
        # Calculator
        if not color:
            calculator = _try_calculator(query)
        # Unit conversion
        if not calculator and not color:
            unit_convert = _try_unit_convert(query)
        # Weather + knowledge panel — run in parallel where possible
        _want_weather = primary and primary.type == "weather"
        _want_knowledge = not dictionary and not calculator and not color and not unit_convert
        if _want_weather and _want_knowledge:
            with ThreadPoolExecutor(max_workers=2) as _card_pool:
                _wf = _card_pool.submit(_try_weather, primary.meta.get("location", ""))
                _kf = _card_pool.submit(_try_knowledge_panel, query)
                try:
                    weather = _wf.result(timeout=4)
                except Exception:
                    weather = None
                if not weather:
                    try:
                        knowledge = _kf.result(timeout=4)
                    except Exception:
                        knowledge = None
                else:
                    _kf.cancel()
        elif _want_weather:
            weather = _try_weather(primary.meta.get("location", ""))
        elif _want_knowledge:
            knowledge = _try_knowledge_panel(query)

    img_extras = _image_search_url_extras(image_opts)
    _intent = query_ui.get("intent", "informational")
    _ai_summary_ok = (
        query_ui.get("show_ai_summary", False) and should_show_ai_summary(query, _intent)
    )
    query_ui = {**query_ui, "show_ai_summary": _ai_summary_ok}
    show_ai_summary_block = search_type == "text" and _ai_summary_ok
    show_answer_layer_block = (
        show_ai_summary_block
        and _feature_allowed("answer_layer", unlocked=current_user_has_paid_access)
    )
    safeguard = (
        search_safeguard_meta(query)
        if (query and page == 1)
        else {"show_crisis_strip": False, "show_inclusive_hint": False, "chaotic_query": False}
    )
    if safeguard.get("show_crisis_strip"):
        show_ai_summary_block = False
        show_answer_layer_block = False
        query_ui = {**query_ui, "show_ai_summary": False}
    return render_template(
        "index.html",
        query=query,
        results=results["results"],
        search_type=search_type,
        has_more=results["has_more"],
        page=1,
        entities=[asdict(e) for e in entities],
        primary_entity=asdict(primary) if primary else None,
        entity_results=entity_results,
        operators=operators,
        region=region or "",
        lang=lang or "",
        dictionary=dictionary,
        qr=qr,
        calculator=calculator,
        color=color,
        unit_convert=unit_convert,
        knowledge=knowledge,
        weather=weather,
        time_filter=time_filter,
        expansion_terms=expansion_terms,
        image_search_advanced=bool(image_opts),
        img_ov_license=(image_opts or {}).get("license", ""),
        img_ov_license_type=(image_opts or {}).get("license_type", ""),
        img_ov_aspect=(image_opts or {}).get("aspect", ""),
        img_ov_size=(image_opts or {}).get("size", ""),
        img_ov_ext=(image_opts or {}).get("extension", ""),
        img_ov_src=",".join((image_opts or {}).get("sources") or []),
        img_src_checked=list((image_opts or {}).get("sources") or ["ddg", "openverse", "commons"]),
        img_scroll_extras=img_extras,
        query_ui=query_ui,
        search_lat=user_lat,
        search_lon=user_lon,
        show_ai_summary_block=show_ai_summary_block,
        show_answer_layer_block=show_answer_layer_block,
        search_notice=results.get("notice"),
        current_user_has_paid_access=current_user_has_paid_access,
        cleanweb=cleanweb,
        safeguard=safeguard,
        osint_enabled=_abbiey_osint_enabled(),
    )
@app.route("/api/suggestions")
@limiter.limit("200/minute")
def api_suggestions():
    """Proxy DuckDuckGo autocomplete to avoid CORS."""
    query = request.args.get("q", "").strip()
    if not query or len(query) > 200:
        return jsonify([])
    try:
        resp = httpx.get(
            "https://duckduckgo.com/ac/",
            params={"q": query, "type": "list"},
            timeout=2.0,
        data = resp.json()
        )
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            return jsonify(data[1][:8])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return jsonify([item["phrase"] for item in data[:8] if "phrase" in item])
        return jsonify([])
    except Exception:
        return jsonify([])


@app.route("/api/entity")
@limiter.limit("120/minute")
def api_entity():
    """API endpoint: detect entities in a query."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify(
            {
                "preprocessing": None,
                "query_ui": None,
                "entities": [],
                "primary": None,
                "queries": [],
            }
        )
    if len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Query too long"}), 400
    prep = preprocess_query(query)
    entities = detect_entities(query, _preprocessed=prep)
    queries = build_search_queries(query, entities)
    primary = primary_entity(entities)
    return jsonify({
        "preprocessing": prep.to_dict(),
        "query_ui": query_ui_hints(prep),
        "entities": [asdict(e) for e in entities],
        "primary": asdict(primary) if primary else None,
        "queries": queries,
    })


@app.route("/api/osint/enrich", methods=["POST"])
@limiter.limit("30/minute")
def api_osint_enrich():
    """On-demand public OSINT (DNS / RDAP / PTR; optional TLS, dig, whois). Not logged as search history."""
    if not _abbiey_osint_enabled():
        return jsonify({"ok": False, "error": "disabled", "facts": [], "modules": [], "entity": None}), 404
    if not request.is_json:
        return jsonify({"ok": False, "error": "json_required", "facts": [], "modules": [], "entity": None}), 400
    data = request.get_json(silent=True) or {}
    q = (data.get("query") or "").strip()
    et = (data.get("entity_type") or "").strip().lower()
    val = (data.get("value") or "").strip()
    if et and val:
        payload = _osint_enrich_run(entity_type=et, value=val)
    elif q:
        payload = _osint_enrich_from_query(q)
    else:
        return jsonify({"ok": False, "error": "missing_body", "facts": [], "modules": [], "entity": None}), 400
    status = 200 if payload.get("ok") else 422
    return jsonify(payload), status


# ---------------------------------------------------------------------------
# Related Searches API
# ---------------------------------------------------------------------------

@app.route("/api/related")
@limiter.limit("120/minute")
def api_related():
    """Return related search suggestions for a query."""
    query = request.args.get("q", "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        return jsonify([])

    related = set()
    try:
        # DDG autocomplete suggestions
        resp = httpx.get(
            "https://duckduckgo.com/ac/",
            params={"q": query, "type": "list"},
            timeout=2.0,
        data = resp.json()
        )
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            for s in data[1]:
                if s.lower() != query.lower():
                    related.add(s)
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            for item in data:
                phrase = item.get("phrase", "")
                if phrase and phrase.lower() != query.lower():
                    related.add(phrase)
    except Exception:
        pass

    # Add variations: "query + how/what/why/vs/alternative"
    suffixes = ["tutorial", "example", "vs", "alternative", "explained"]
    for suffix in suffixes:
        candidate = f"{query} {suffix}"
        if candidate.lower() != query.lower():
            related.add(candidate)

    # Also try partial terms for broader suggestions
    words = query.split()
    if len(words) > 1:
        for word in words:
            if len(word) > 3:
                try:
                    resp2 = httpx.get(
                        "https://duckduckgo.com/ac/",
                        params={"q": word, "type": "list"},
                        timeout=1.5,
                    d2 = resp2.json()
                    )
                    if isinstance(d2, list) and len(d2) > 1 and isinstance(d2[1], list):
                        for s in d2[1][:3]:
                            if s.lower() != query.lower() and s.lower() != word.lower():
                                related.add(s)
                    break  # Only do one subword to stay fast
                except Exception:
                    pass

    result = list(related)[:12]
    return jsonify(result)


# ---------------------------------------------------------------------------
# Result Preview API
# ---------------------------------------------------------------------------

@app.route("/api/onion-proxy")
@limiter.limit("60/minute")
def api_onion_proxy():
    """Proxy .onion URLs through local Tor SOCKS5 (if running on port 9050)."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL specified"}), 400

    parsed = urlparse(url)
    if not parsed.hostname or not parsed.hostname.endswith(".onion"):
        return jsonify({"error": "Only .onion URLs are allowed"}), 400

    try:
        import httpx
        # Route through Tor SOCKS5 proxy
        transport = httpx.HTTPTransport(proxy="socks5://127.0.0.1:9050")
        with httpx.Client(transport=transport, timeout=30.0, follow_redirects=True) as client:
            resp = client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0"},
            )
        from flask import Response
        # Pass through content, rewriting internal .onion links to also go through proxy
        content = resp.text
        content = re.sub(
            r'(href|src|action)="(https?://[^"]*\.onion[^"]*)"',
            r'\1="/api/onion-proxy?url=\2"',
            content,
        )
        return Response(content, content_type=resp.headers.get("content-type", "text/html"))
    except Exception:
        logger.exception("onion_proxy_failed url=%s", url[:200] if url else "")
        from html import escape as _esc
        safe_url = _esc(url, quote=True)
        return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Onion service unavailable</title></head>
<body style="background:#0a0a0a;color:#e4e4e7;font-family:system-ui;line-height:1.5;padding:2rem;max-width:36rem;margin:0 auto">
<p style="font-size:1.05rem;margin:0 0 1rem">We couldn&rsquo;t open that onion service from this browser. If you use Tor, open the link in Tor Browser instead.</p>
<details style="color:#a1a1aa;font-size:.9rem;margin-top:1.25rem">
<summary style="cursor:pointer;color:#d4d4d8">Troubleshooting</summary>
<ul style="margin:.75rem 0 0;padding-left:1.2rem">
<li>This app proxies onion sites only when a Tor SOCKS proxy is available (often port 9050).</li>
<li>Tor Browser includes Tor; a standalone <code style="background:#27272a;padding:0 .2em;border-radius:3px">tor</code> daemon also works.</li>
<li>Requested address: <code style="word-break:break-all">{safe_url}</code></li>
</ul>
<p style="margin:.75rem 0 0"><a href="{safe_url}" style="color:#a78bfa">Try in Tor Browser &rarr;</a></p>
</details>
</body></html>""", 502


# ---------------------------------------------------------------------------
# Onion Link Verification API
# ---------------------------------------------------------------------------

_ONION_HOST_RE = re.compile(r"^[a-z2-7]{16,56}\.onion$")


def _check_single_onion(url):
    """Check a single .onion URL via local Tor SOCKS proxy. Returns (url, status).

    Requires Tor running on port 9050.  If Tor is not available, returns
    "unknown" so the frontend doesn't show misleading live/down badges.
    """
    # Check cache first
    with _onion_status_lock:
        cached = _onion_status_cache.get(url)
    if cached is not None:
        return url, cached

    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not _ONION_HOST_RE.match(hostname):
        return url, "down"

    try:
        transport = httpx.HTTPTransport(proxy="socks5://127.0.0.1:9050")
        with httpx.Client(transport=transport, timeout=10.0, follow_redirects=True) as client:
            resp = client.head(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0"},
        status = "live" if resp.status_code < 400 else "down"
            )
    except Exception:
        # Tor not running or site unreachable — can't distinguish, report unknown
        status = "unknown"

    if status != "unknown":
        with _onion_status_lock:
            _onion_status_cache[url] = status
    return url, status


@app.route("/api/onion-check", methods=["POST"])
@limiter.limit("80/minute")
def api_onion_check():
    """Check reachability of .onion URLs via Tor2web gateway."""
    data = request.get_json(silent=True) or {}
    urls = data.get("urls", [])

    if not isinstance(urls, list) or not urls:
        return jsonify({"error": "Provide a list of URLs"}), 400

    # Cap to 30 URLs per request
    urls = [u for u in urls[:30] if isinstance(u, str) and u.startswith("http")]

    results = {}
    # Return cached results immediately, queue uncached for checking
    uncached = []
    for url in urls:
        with _onion_status_lock:
            cached = _onion_status_cache.get(url)
        if cached is not None:
            results[url] = cached
        else:
            uncached.append(url)

    # Check uncached URLs in parallel
    if uncached:
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_check_single_onion, u): u for u in uncached}
            for future in as_completed(futures):
                try:
                    url, status = future.result()
                    results[url] = status
                except Exception:
                    results[futures[future]] = "down"

    return jsonify({"results": results})


def _is_private_ip(hostname):
    """Check if a hostname resolves to a private/internal IP."""
    import socket
    import ipaddress
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return True
    except (socket.gaierror, ValueError):
        return False
    return False


@app.route("/api/preview")
@limiter.limit("120/minute")
def api_preview():
    """Fetch a page preview (title + description + text excerpt)."""
    url = request.args.get("url", "").strip()
    if url.startswith("//"):
        url = "https:" + url
    if not url or not url.startswith("http"):
        return jsonify({"error": _PREVIEW_MSG_INVALID}), 400
    if len(url) > _MAX_PREVIEW_URL_LEN:
        return jsonify({"error": _PREVIEW_MSG_LONG}), 400
    parsed_preview = urlparse(url)
    if ".onion" in (parsed_preview.netloc or ""):
        return jsonify({"error": _PREVIEW_MSG_ONION}), 400
    hostname = parsed_preview.hostname or ""
    if not hostname or _is_private_ip(hostname):
        return jsonify({"error": _PREVIEW_MSG_PRIVATE}), 400

    try:
        resp = httpx.get(
            url,
            timeout=4.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; abbiey.search/1.0)"},
        # Guard against redirect-based SSRF: validate final URL after redirects
        )
        final_url = str(resp.url)
        final_parsed = urlparse(final_url)
        final_host = final_parsed.hostname or ""
        if not final_host or _is_private_ip(final_host):
            return jsonify({"error": _PREVIEW_MSG_PRIVATE}), 400
        if ".onion" in (final_parsed.netloc or ""):
            return jsonify({"error": _PREVIEW_MSG_ONION}), 400
        resp.raise_for_status()
        html = resp.text[:100000]  # Cap at 100KB

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", title_match.group(1).strip()) if title_match else ""

        # Extract meta description
        desc_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE | re.DOTALL
        )
        if not desc_match:
            desc_match = re.search(
                r'<meta[^>]*content=["\'](.*?)["\'][^>]*name=["\']description["\']',
                html, re.IGNORECASE | re.DOTALL
            )
        description = re.sub(r"\s+", " ", desc_match.group(1).strip()) if desc_match else ""

        # Extract OG image
        og_img_match = re.search(
            r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        if not og_img_match:
            og_img_match = re.search(
                r'<meta[^>]*content=["\'](.*?)["\'][^>]*property=["\']og:image["\']',
                html, re.IGNORECASE
            )
        og_image = og_img_match.group(1).strip() if og_img_match else ""

        # Extract text content (strip tags, get first ~500 chars)
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # Find the most informative paragraph (skip short lines)
        excerpt = ""
        for chunk in text.split(". "):
            chunk = chunk.strip()
            if len(chunk) > 60:
                excerpt = chunk[:500]
                break
        if not excerpt:
            excerpt = text[:500]

        # Extract site name
        site_match = re.search(
            r'<meta[^>]*property=["\']og:site_name["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        site_name = site_match.group(1).strip() if site_match else ""

        return jsonify({
            "title": title[:200],
            "description": description[:500],
            "excerpt": excerpt,
            "image": og_image,
            "site_name": site_name,
            "url": url,
        })
    except httpx.TimeoutException:
        _log_event("preview_fetch_timeout")
        return jsonify({"error": _PREVIEW_MSG_TIMEOUT}), 504
    except httpx.HTTPStatusError as e:
        code = e.response.status_code if e.response is not None else "?"
        _log_event("preview_fetch_http_error", status=code)
        logger.warning("preview_fetch_http_error url=%s status=%s", url[:120], code)
        return jsonify({"error": _PREVIEW_MSG_UNAVAILABLE}), 502
    except Exception:
        logger.exception("preview_fetch_failed")
        return jsonify({"error": _PREVIEW_MSG_UNAVAILABLE}), 502


# ---------------------------------------------------------------------------
# AI Research Assistant Chat
# ---------------------------------------------------------------------------

def _ollama_chat(messages, model=None, timeout=30.0):
    """AI chat using local Ollama instance."""
    _model = model or OLLAMA_MODEL
    try:
        resp = _get_http().post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": _model, "messages": messages, "stream": False},
            timeout=float(timeout),
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Ollama unavailable: {e}") from e


# ---- Answer Layer: structured multi-source synthesis (JSON from LLM) ----
ANSWER_LAYER_MAX_SOURCES = 10
ANSWER_LAYER_SNIPPET_LEN = 480

# ---- AI summary: context window (snippet caps keep prompts bounded) ----
_AI_SUMMARY_MAX_SOURCES_SIMPLE = 5
_AI_SUMMARY_MAX_SOURCES_STANDARD = 8
_AI_SUMMARY_BODY_CHARS = 400


def _parse_llm_json_object(raw: str) -> dict | None:
    """Extract a JSON object from model output (handles ```json fences)."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
        s = re.sub(r"\s*```\s*$", "", s)
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}\s*$", s)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_answer_layer_payload(data: dict, num_sources: int) -> dict:
    """Clamp and validate Answer Layer fields for safe JSON → UI."""
    out = {
        "headline": (data.get("headline") or data.get("title") or "").strip()[:200],
        "synthesis": (data.get("synthesis") or data.get("answer") or data.get("body") or "").strip()[:5500],
        "claims": [],
        "contradictions": [],
        "reasoning_steps": [],
    }

    def _clean_indices(xs, cap=8):
        if not isinstance(xs, list):
            return []
        o = []
        for x in xs[:cap]:
            try:
                xi = int(x)
                if 1 <= xi <= num_sources:
                    o.append(xi)
            except (TypeError, ValueError):
                continue
        return o

    for c in data.get("claims") or []:
        if not isinstance(c, dict):
            continue
        stmt = (c.get("statement") or c.get("claim") or "").strip()
        if not stmt:
            continue
        try:
            conf = float(c.get("confidence", 0.65))
        except (TypeError, ValueError):
            conf = 0.65
        conf = max(0.0, min(1.0, conf))
        out["claims"].append(
            {
                "statement": stmt[:800],
                "confidence": conf,
                "source_indices": _clean_indices(c.get("source_indices") or c.get("citations") or [], 6),
            }
        )

    for z in data.get("contradictions") or []:
        if not isinstance(z, dict):
            continue
        summ = (z.get("summary") or z.get("topic") or "").strip()
        a = (z.get("position_a") or z.get("view_a") or "").strip()
        b = (z.get("position_b") or z.get("view_b") or "").strip()
        if not summ and not (a and b):
            continue
        sa = z.get("sources_a") or z.get("source_indices_a") or []
        sb = z.get("sources_b") or z.get("source_indices_b") or []
        out["contradictions"].append(
            {
                "summary": (summ or "Sources disagree on this point.")[:400],
                "position_a": a[:600],
                "position_b": b[:600],
                "sources_a": _clean_indices(sa, 4),
                "sources_b": _clean_indices(sb, 4),
            }
        )

    for r in data.get("reasoning_steps") or data.get("reasoning") or []:
        if isinstance(r, str):
            r = {"step": r, "source_indices": []}
        if not isinstance(r, dict):
            continue
        step = (r.get("step") or r.get("text") or "").strip()
        if not step:
            continue
        out["reasoning_steps"].append(
            {"step": step[:500], "source_indices": _clean_indices(r.get("source_indices") or [], 8)}
        )

    return out


def _extractive_research(question, results):
    """Fallback: build a research answer from search results without AI.
    Matches the question keywords against results and builds a cited summary.
    """
    if not results:
        return "I couldn't find any search results to research this topic."

    # Tokenize question into keywords (lowercase, skip short/stop words)
    stop = {"the", "a", "an", "is", "are", "was", "were", "what", "who", "when",
            "where", "why", "how", "do", "does", "did", "can", "could", "will",
            "would", "should", "for", "of", "in", "on", "at", "to", "and", "or",
            "but", "not", "it", "this", "that", "with", "from", "by", "about", "be"}
    keywords = [w.lower() for w in re.split(r"\W+", question) if len(w) > 2 and w.lower() not in stop]

    if not keywords:
        keywords = [w.lower() for w in re.split(r"\W+", question) if len(w) > 1]

    # Score each result by keyword overlap
    scored = []
    for r in results:
        text = f"{r.get('title', '')} {r.get('body', '')}".lower()
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scored.append((hits, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        # No keyword matches — return all results as general context
        scored = [(0, r) for r in results[:5]]

    # Build response from top matching results
    parts = [f"Based on the search results, here's what I found:\n"]
    for i, (_, r) in enumerate(scored[:5], 1):
        title = r.get("title", "Untitled")
        body = r.get("body", "")
        url = r.get("url", "")

        # Trim body to a reasonable length
        if len(body) > 300:
            body = body[:297] + "..."

        parts.append(f"**{i}. {title}**")
        if body:
            parts.append(f"{body}")
        if url:
            parts.append(f"Source: {url}")
        parts.append("")

    if len(scored) > 5:
        parts.append(f"*Found {len(scored)} relevant results total. Ask me to dig deeper into any of these.*")

    return "\n".join(parts)


@app.route("/api/chat", methods=["POST"])
@limiter.limit("80/minute")
def api_chat():
    """AI research assistant that studies search results and answers questions."""
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not query or not message:
        return jsonify({"error": _CHAT_MSG_MISSING}), 400
    if len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": _CHAT_MSG_QUERY_LONG}), 400
    if len(message) > _MAX_CHAT_MESSAGE_LEN:
        return jsonify({"error": _CHAT_MSG_MESSAGE_LONG}), 400
    if not isinstance(history, list):
        return jsonify({"error": _CHAT_MSG_HISTORY}), 400
    if len(history) > _MAX_CHAT_HISTORY_TURNS * 2:
        history = history[-(_MAX_CHAT_HISTORY_TURNS * 2) :]
    for h in history:
        if not isinstance(h, dict):
            return jsonify({"error": _CHAT_MSG_HISTORY}), 400
        role = h.get("role", "")
        content = h.get("content", "")
        if role not in ("user", "assistant"):
            return jsonify({"error": _CHAT_MSG_HISTORY}), 400
        if not isinstance(content, str) or len(content) > _MAX_CHAT_MESSAGE_LEN:
            return jsonify({"error": _CHAT_MSG_HISTORY}), 400

    # Fetch search results for context
    context_results = _fetch_results(query, 1, "text")
    # Build context from top results
    context_lines = [f"Search results for '{query}':\n"]
    for i, r in enumerate(context_results["results"][:5], 1):
        context_lines.append(
            f"{i}. {r.get('title', '')}\n"
            f"   URL: {r.get('url', '')}\n"
            f"   {r.get('body', '')}\n"
        )
    context = "\n".join(context_lines)

    system_context = (
        "You are a research assistant. Use the provided search results to answer questions. "
        "Quote relevant passages and cite sources by number.\n\n"
        + context
    )
    # Build messages list for the AI chat API
    messages = [{"role": "system", "content": system_context}]
    messages.append({"role": "assistant", "content": f"I've studied the search results about '{query}'. What would you like to know?"})

    for h in history[-6:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    # Try AI chat first, fall back to extractive research
    try:
        response = _ollama_chat(messages)
        if not response:
            raise RuntimeError("Empty AI response")
        return jsonify({"response": response})
    except Exception:
        logger.warning("AI chat unavailable, using extractive research fallback")

    # Fallback: extractive research from search results
    try:
        # For follow-up questions, also search for the specific question
        all_results = list(context_results["results"])
        if message.lower() != query.lower():
            extra = _fetch_results(f"{query} {message}", 1, "text")
            all_results.extend(extra["results"])
            all_results = _deduplicate(all_results)
        response = _extractive_research(message, all_results)
        return jsonify({"response": response})
    except Exception:
        logger.exception("chat_fallback_failed")
        return jsonify({"error": _CHAT_MSG_UNAVAILABLE}), 503


@app.route("/api/answer-layer")
@limiter.limit("40 per minute")
def api_answer_layer():
    """Structured multi-source answer: synthesis, claims with confidence, contradictions, reasoning."""
    query = (request.args.get("q") or "").strip()
    region = (request.args.get("region") or "").strip()
    lang = (request.args.get("lang") or "").strip()
    cleanweb = request.args.get("cleanweb", "").strip().lower() in ("1", "true", "yes", "on")
    anti_template = bool(cleanweb)

    if not query or len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Invalid query"}), 400

    current_uid = _session_user_id_int(session.get("user_id"))
    unlocked = _search_access_granted(uid=current_uid, token=_search_unlock_cookie_token())
    prep = preprocess_query(query)
    if not should_enable_ai_summary(prep):
        return jsonify({"enabled": False, "layer": False, "clarify": detect_query_clarification(prep)}), 200
    if not should_show_ai_summary(query, prep.intent):
        return jsonify({"enabled": False, "layer": False, "clarify": detect_query_clarification(prep)}), 200

    safeguard = search_safeguard_meta(query)
    if safeguard.get("show_crisis_strip"):
        return jsonify({"enabled": False, "message": "AI summary is not available for this query."}), 200

    if not _feature_allowed("answer_layer", unlocked=unlocked):
        return jsonify({"enabled": True, "layer": False}), 200

    user_lat = _parse_request_coord("lat")
    user_lon = _parse_request_coord("lon")
    if user_lat is not None and not (-90 <= user_lat <= 90):
        user_lat = None
    if user_lon is not None and not (-180 <= user_lon <= 180):
        user_lon = None
    anchor_geo = None
    if user_lat is not None and user_lon is not None and has_local_intent_signals(prep):
        anchor_geo = _reverse_geocode_label(user_lat, user_lon)
    loc_ctx = resolve_location_for_search(prep, user_lat, user_lon, anchor_geo)
    backend_q = build_backend_search_query(query, prep, loc_ctx)

    try:
        payload = _fetch_results(
            backend_q,
            1,
            "text",
            region or None,
            lang or None,
            anti_template=anti_template,
            local_rank_context=loc_ctx if loc_ctx.get("has_local_intent") else None,
            source_query_for_fallback=query,
        )
    except Exception as e:
        logger.exception("answer_layer_fetch_failed")
        return jsonify({"enabled": True, "layer": False, "error": str(e)}), 200

    organic = payload.get("results") or []
    if not organic:
        return jsonify(
            {
                "enabled": True,
                "layer": False,
                "error": "unavailable",
                "message": _AI_SUMMARY_MSG_NO_CONTEXT,
                "clarify": detect_query_clarification(prep),
            }
        ), 404

    top = organic[:ANSWER_LAYER_MAX_SOURCES]
    lines = []
    for i, r in enumerate(top, start=1):
        title = (r.get("title") or "")[:200]
        url = (r.get("url") or "")[:500]
        body = (r.get("body") or "")[:ANSWER_LAYER_SNIPPET_LEN]
        lines.append(f"[{i}] {title}\nURL: {url}\nSnippet: {body}")

    bundle = "\n\n".join(lines)
    sys_prompt = (
        "You are an expert research synthesizer. Output ONLY a single valid JSON object—no markdown fences, "
        "no commentary before or after. Escape quotes inside strings properly.\n\n"
        "Grounding (critical): Every substantive statement in synthesis and claims must be supported by "
        "the numbered snippets. Do not invent facts, dates, numbers, or quotes. If evidence is thin, say so "
        "in the synthesis and use lower confidence. If you are inferring, label it as inference in the claim "
        "text and lower confidence.\n\n"
        "Schema:\n"
        "{\n"
        '  "headline": "neutral, specific title (max 12 words); no clickbait",\n'
        '  "synthesis": "2–4 paragraphs, plain text, no URLs. Paragraph 1: direct, precise answer to the '
        'user question. Later paragraphs: important context, limits of knowledge, who/when/where if relevant.",\n'
        '  "claims": [\n'
        '    {"statement": "one atomic factual claim", "confidence": 0.0-1.0, "source_indices": [1,2]}\n'
        "  ],\n"
        '  "contradictions": [\n'
        '    {"summary": "one line: what is disputed", "position_a": "...", "position_b": "...", '
        '"sources_a": [1], "sources_b": [2]}\n'
        "  ],\n"
        '  "reasoning_steps": [\n'
        '    {"step": "specific step: what you read, what agreed/disagreed, how you merged it", '
        '"source_indices": [1,3]}\n'
        "  ]\n"
        "}\n\n"
        "Quality rules:\n"
        "- claims: 4–10 items when snippets allow; each claim needs at least one source_index.\n"
        "- confidence: high (0.75–1.0) only when 2+ independent sources agree or one authoritative snippet "
        "is explicit; medium 0.45–0.74 for single-source or partial evidence; low below 0.45 when weak or disputed.\n"
        "- contradictions: [] if sources align; otherwise capture real tensions visible in snippets (not trivia).\n"
        "- reasoning_steps: 4–7 concrete steps tracing sources → conclusions.\n"
        "- Use source_indices 1–N only (matching the bundle)."
    )
    user_prompt = (
        f"User question: {query}\n\n"
        "Instructions: Answer the question using ONLY the sources below. Prefer accuracy over flair. "
        "If the question is ambiguous, address the most likely meaning and note uncertainty in synthesis.\n\n"
        f"Sources (numbered):\n{bundle}"
    )

    try:
        raw = _ollama_chat(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=55.0,
        )
    except Exception as e:
        logger.warning("answer_layer_ollama_failed: %s", e)
        return jsonify({"enabled": True, "layer": False}), 200

    parsed = _parse_llm_json_object(raw)
    if not parsed:
        return jsonify({"enabled": True, "layer": False}), 200

    layer = _normalize_answer_layer_payload(parsed, len(top))
    if not layer.get("synthesis") and not layer.get("claims"):
        return jsonify({"enabled": True, "layer": False}), 200

    sources_out = []
    for i, r in enumerate(top, start=1):
        sources_out.append(
            {
                "index": i,
                "title": (r.get("title") or "")[:300],
                "url": r.get("url") or "",
                "hostname": r.get("hostname") or "",
            }
        )

    return jsonify(
        {
            "enabled": True,
            "layer": True,
            "query": query,
            "headline": layer["headline"],
            "synthesis": layer["synthesis"],
            "claims": layer["claims"],
            "contradictions": layer["contradictions"],
            "reasoning_steps": layer["reasoning_steps"],
            "sources": sources_out,
        }
    )


@app.route("/api/ai-summary")
@limiter.limit("80/minute")
def api_ai_summary():
    """Generate a 2-3 sentence AI summary with citations for a query."""
    query = request.args.get("q", "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Invalid query"}), 400

    prep = preprocess_query(query)
    if not should_enable_ai_summary(prep):
        return jsonify({"enabled": False, "clarify": detect_query_clarification(prep)})
    if not should_show_ai_summary(query, prep.intent):
        return jsonify({"enabled": False, "clarify": detect_query_clarification(prep)})

    clarify = detect_query_clarification(prep)
    simple = is_simple_answer_query(query, clarify)

    user_lat = _parse_request_coord("lat")
    user_lon = _parse_request_coord("lon")
    if user_lat is not None and not (-90 <= user_lat <= 90):
        user_lat = None
    if user_lon is not None and not (-180 <= user_lon <= 180):
        user_lon = None
    anchor_geo = None
    if user_lat is not None and user_lon is not None and has_local_intent_signals(prep):
        anchor_geo = _reverse_geocode_label(user_lat, user_lon)
    loc_ctx = resolve_location_for_search(prep, user_lat, user_lon, anchor_geo)
    backend_q = build_backend_search_query(query, prep, loc_ctx)

    _n_ctx = _AI_SUMMARY_MAX_SOURCES_SIMPLE if simple else _AI_SUMMARY_MAX_SOURCES_STANDARD
    context_results = _fetch_results(
        backend_q, 1, "text", local_rank_context=loc_ctx if loc_ctx.get("has_local_intent") else None
    )
    top5 = context_results["results"][:_n_ctx]
    if not top5:
        return jsonify(
            {
                "enabled": True,
                "error": "unavailable",
                "message": _AI_SUMMARY_MSG_NO_CONTEXT,
                "clarify": clarify,
                "answer_mode": "single" if simple else "standard",
            }
        ), 404

    # Build context (truncated bodies so the model focuses on on-SERP evidence)
    context_lines = []
    sources = []
    for i, r in enumerate(top5, 1):
        title = (r.get("title") or "").strip()
        body = (r.get("body") or "").strip()
        if len(body) > _AI_SUMMARY_BODY_CHARS:
            body = body[: _AI_SUMMARY_BODY_CHARS].rsplit(" ", 1)[0] + "…"
        url = r.get("url", "")
        context_lines.append(f"[{i}] {title}\n    Snippet: {body}")
        sources.append({"title": title, "url": url})
    context = "\n".join(context_lines)

    _ground = (
        "You only use information from the numbered snippets. Do not invent facts, statistics, or quotes. "
        "If snippets are insufficient, say only what they support and avoid filling gaps. "
        "If snippets disagree, mention that briefly. Cite [n] only for claims those snippets support."
    )
    if simple:
        system_msg = (
            "You are a precise search assistant. " + _ground + " "
            "Reply with at most 2 short sentences total. The first sentence must answer the question outright. "
            "Cite as [1], [2] where needed. No bullet lists. No preamble (e.g. no \"Based on the results\")."
        )
    elif clarify:
        system_msg = (
            "You are a precise search assistant. " + _ground + " "
            "The query may name an ambiguous topic. Answer for the most likely interpretation in 2 short sentences, "
            "then one brief sentence noting other common meanings exist. Cite [1], [2]."
        )
    else:
        system_msg = (
            "You are a precise search assistant. " + _ground + " "
            "Write 2–4 sentences: lead with the clearest direct answer, then add one or two sentences of "
            "useful context (scope, caveats, or timeframe) only if supported by the snippets. "
            "Cite sources as [1], [2]. Be concise; avoid generic filler."
        )
    try:
        summary_messages = [
            {"role": "system", "content": system_msg},
            {
                "role": "user",
                "content": f"Query: {query}\n\nWeb snippets:\n{context}",
            },
        ]
        response = _ollama_chat(summary_messages)
        if response:
            return jsonify(
                {
                    "summary": response,
                    "sources": sources,
                    "answer_mode": "single" if simple else "standard",
                    "clarify": clarify,
                }
            )
    except Exception:
        _log_event("ai_summary_ollama_failed", fallback="extractive")

    # Fallback: extractive summary from first two results
    parts = []
    for i, r in enumerate(top5[:2], 1):
        body = r.get("body", "")
        if body:
            parts.append(f"{body} [{i}]")
    if parts:
        return jsonify(
            {
                "summary": " ".join(parts),
                "sources": sources,
                "answer_mode": "single" if simple else "standard",
                "clarify": clarify,
            }
        )

    return jsonify(
        {
            "enabled": True,
            "error": "unavailable",
            "message": _AI_SUMMARY_MSG_UNAVAILABLE,
            "clarify": clarify,
            "answer_mode": "single" if simple else "standard",
        }
    ), 503


@app.route("/api/waitlist", methods=["POST"])
@limiter.limit("40/minute")
def api_waitlist():
    """Store an email address for the waitlist/update notifications."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email or len(email) > 254:
        return jsonify({"error": "Invalid email address"}), 400
    try:
        _waitlist_execute("INSERT INTO waitlist (email) VALUES (?)", [email])
        return jsonify({"ok": True})
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg or "already exists" in msg:
            return jsonify({"ok": True})  # Already on list — treat as success
        logger.error("Waitlist insert failed: %s", exc)
        return jsonify(
            {"ok": False, "error": "Could not save your email right now. Please try again later."}
        ), 503


# ---------------------------------------------------------------------------
# Analytics & Trends API
# ---------------------------------------------------------------------------
@app.route("/api/privacy-stats")
@limiter.limit("200/minute")
def api_privacy_stats():
    """Returns real, server-confirmed privacy stats. All zeros reflect genuine policy."""
    total_queries = 0
    try:
        rows = _analytics_execute("SELECT COUNT(*) as cnt FROM search_logs")
        total_queries = rows[0]["cnt"] if rows else 0
    except Exception:
        pass
    return jsonify({
        "trackers": 0,          # no tracking scripts or pixels used
        "personal_data": 0,     # no personal data stored (queries logged anonymously)
        "third_party_shared": 0, # no data sold or shared with third parties
        "total_queries": total_queries,  # total anonymous queries processed
    })


# ---------------------------------------------------------------------------
@app.route("/api/trends")
@limiter.limit("120/minute")
def api_trends():
    """Public endpoint — returns top 10 trending queries from the last 24 h."""
    try:
        rows = _analytics_execute(
            "SELECT query, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now', '-1 day')"
            "   AND search_type = 'text'"
            "   AND length(query) BETWEEN 2 AND 80"
            " GROUP BY lower(query) ORDER BY cnt DESC LIMIT 10"
        )
        return jsonify([{"query": r["query"], "count": r["cnt"]} for r in rows])
    except Exception as exc:
        logger.error("Trends error: %s", exc)
        return jsonify([])


@app.route("/admin/analytics")
def admin_analytics():
    """Admin analytics dashboard — protected by ADMIN_TOKEN query param."""
    token = request.args.get("token", "")
    if not _ADMIN_TOKEN or token != _ADMIN_TOKEN:
        return render_template("error.html", code=403, title="Forbidden",
                               message="Invalid or missing admin token."), 403

    import datetime as _dt
    stats = {}
    try:
        rows = _analytics_execute("SELECT COUNT(*) as cnt FROM search_logs")
        stats["total_all_time"] = rows[0]["cnt"] if rows else 0

        rows = _analytics_execute(
            "SELECT COUNT(*) as cnt FROM search_logs WHERE created_at >= date('now')")
        stats["total_today"] = rows[0]["cnt"] if rows else 0

        rows = _analytics_execute(
            "SELECT COUNT(*) as cnt FROM search_logs WHERE created_at >= datetime('now','-7 days')")
        stats["total_week"] = rows[0]["cnt"] if rows else 0

        # Top queries (7 days) — as (query, cnt) tuples for template
        raw = _analytics_execute(
            "SELECT query, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days')"
            "   AND length(query) BETWEEN 2 AND 80"
            " GROUP BY lower(query) ORDER BY cnt DESC LIMIT 20")
        stats["top_queries"] = [(r["query"], r["cnt"]) for r in raw]

        # Tab distribution
        raw = _analytics_execute(
            "SELECT search_type, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days')"
            " GROUP BY search_type ORDER BY cnt DESC")
        stats["by_type"] = [(r["search_type"], r["cnt"]) for r in raw]

        # Hourly distribution (last 7 days)
        raw = _analytics_execute(
            "SELECT hour, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days')"
            " GROUP BY hour ORDER BY hour")
        stats["by_hour"] = [(r["hour"], r["cnt"]) for r in raw]

        # Daily volume (last 30 days)
        raw = _analytics_execute(
            "SELECT date(created_at) as day, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-30 days')"
            " GROUP BY day ORDER BY day")
        stats["daily"] = [(r["day"], r["cnt"]) for r in raw]

        # Top regions
        raw = _analytics_execute(
            "SELECT region, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days') AND region != ''"
            " GROUP BY region ORDER BY cnt DESC LIMIT 10")
        stats["top_regions"] = [(r["region"], r["cnt"]) for r in raw]

        # Build hourly heatmap (fill missing hours with 0)
        hour_map = {r[0]: r[1] for r in stats["by_hour"]}
        stats["hours"] = [(h, hour_map.get(h, 0)) for h in range(24)]
        max_hour = max((v for _, v in stats["hours"]), default=1) or 1
        stats["hours_pct"] = [(h, round(v / max_hour * 100)) for h, v in stats["hours"]]

        # Daily chart
        daily_map = {r[0]: r[1] for r in stats["daily"]}
        today = _dt.date.today()
        stats["daily_chart"] = [
            ((today - _dt.timedelta(days=29 - i)).isoformat(),
             daily_map.get((today - _dt.timedelta(days=29 - i)).isoformat(), 0))
            for i in range(30)
        ]
        max_daily = max((v for _, v in stats["daily_chart"]), default=1) or 1
        stats["daily_pct"] = [(d, v, round(v / max_daily * 100)) for d, v in stats["daily_chart"]]

    except Exception as exc:
        logger.error("Analytics dashboard error: %s", exc)
        stats["error"] = str(exc)

    return render_template("analytics.html", stats=stats)


# ---------------------------------------------------------------------------
# Admin Dashboard — full command centre with AI chatbot
# ---------------------------------------------------------------------------

def _admin_check():
    """Return None if authorised, else an error Response."""
    if not _ADMIN_TOKEN:
        return jsonify({"error": "Forbidden — ADMIN_TOKEN not configured"}), 403
    token = request.args.get("token", "") or request.headers.get("X-Admin-Token", "")
    if not token or token != _ADMIN_TOKEN:
        return jsonify({"error": "Forbidden"}), 403
    return None


@app.route("/admin")
def admin_dashboard():
    """Main admin dashboard — protected by ADMIN_TOKEN."""
    token = request.args.get("token", "")
    if not _ADMIN_TOKEN or token != _ADMIN_TOKEN:
        return render_template("error.html", code=403, title="Forbidden",
                               message="Admin access only."), 403
    return render_template("admin.html", token=token)


@app.route("/admin/api/stats")
def admin_api_stats():
    """JSON stats endpoint for the admin dashboard — real data, Turso or SQLite."""
    err = _admin_check()
    if err:
        return err
    import datetime as _dt
    data = {"storage": _active_storage()}
    try:
        def _scalar(sql, args=None):
            rows = _analytics_execute(sql, args or [])
            if rows:
                v = list(rows[0].values())[0]
                return v
            return 0

        data["searches_today"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs WHERE created_at >= date('now')")
        data["searches_week"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs WHERE created_at >= datetime('now','-7 days')")
        data["searches_total"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs")
        data["searches_last_hour"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs WHERE created_at >= datetime('now','-1 hour')")
        data["searches_last_5min"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs WHERE created_at >= datetime('now','-5 minutes')")
        data["avg_latency_ms"] = _scalar(
            "SELECT ROUND(AVG(latency_ms)) as c FROM search_logs"
            " WHERE latency_ms > 0 AND created_at >= datetime('now','-7 days')") or 0
        data["p95_latency_ms"] = _scalar(
            "SELECT latency_ms as c FROM search_logs WHERE latency_ms > 0"
            " AND created_at >= datetime('now','-7 days')"
            " ORDER BY latency_ms LIMIT 1 OFFSET MAX(0,"
            "(SELECT COUNT(*)*95/100 FROM search_logs WHERE latency_ms > 0"
            " AND created_at >= datetime('now','-7 days'))-1)") or 0
        data["errors_today"] = _scalar(
            "SELECT COUNT(*) as c FROM error_logs WHERE created_at >= date('now')")
        data["errors_week"] = _scalar(
            "SELECT COUNT(*) as c FROM error_logs WHERE created_at >= datetime('now','-7 days')")

        # Top queries (7 days)
        data["top_queries"] = _analytics_execute(
            "SELECT query, COUNT(*) as count FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days') AND length(query) BETWEEN 2 AND 80"
            " GROUP BY lower(query) ORDER BY count DESC LIMIT 15")

        # Type breakdown (7 days)
        data["by_type"] = _analytics_execute(
            "SELECT search_type as type, COUNT(*) as count FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days')"
            " GROUP BY search_type ORDER BY count DESC")

        # Daily chart (30 days) — fill zeros for missing days
        today = _dt.date.today()
        raw_daily = _analytics_execute(
            "SELECT date(created_at) as d, COUNT(*) as count FROM search_logs"
            " WHERE created_at >= datetime('now','-30 days') GROUP BY d ORDER BY d")
        daily_map = {r["d"]: int(r["count"]) for r in raw_daily}
        data["daily"] = [
            {"date": (today - _dt.timedelta(days=29 - i)).isoformat(),
             "count": daily_map.get((today - _dt.timedelta(days=29 - i)).isoformat(), 0)}
            for i in range(30)
        ]

        # Hourly heatmap (7 days)
        raw_hourly = _analytics_execute(
            "SELECT hour, COUNT(*) as count FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days') GROUP BY hour")
        hour_map = {int(r["hour"]): int(r["count"]) for r in raw_hourly}
        data["hourly"] = [{"hour": h, "count": hour_map.get(h, 0)} for h in range(24)]

        # Recent searches (50) — includes client metadata when columns exist
        data["recent_searches"] = _analytics_execute(
            "SELECT query, search_type as type, result_count as results,"
            " latency_ms, created_at as ts, client_ip, user_agent, device_label, location"
            " FROM search_logs ORDER BY id DESC LIMIT 50")

        # User stats
        try:
            rows = _users_execute("SELECT COUNT(*) as cnt FROM users")
            data["total_users"] = rows[0]["cnt"] if rows else 0
            rows = _users_execute(
                "SELECT COUNT(*) as cnt FROM users WHERE created_at >= date('now')")
            data["users_today"] = rows[0]["cnt"] if rows else 0
            rows = _users_execute(
                "SELECT COUNT(*) as cnt FROM users WHERE created_at >= datetime('now','-7 days')")
            data["users_week"] = rows[0]["cnt"] if rows else 0
            rows = _users_execute("SELECT COUNT(*) as cnt FROM user_search_history")
            data["account_history_rows"] = int(rows[0]["cnt"]) if rows else 0
        except Exception:
            data["total_users"] = 0
            data["users_today"] = 0
            data["users_week"] = 0
            data["account_history_rows"] = 0

        # Error logs (100 most recent)
        data["error_logs"] = _analytics_execute(
            "SELECT route, level, message, created_at as ts FROM error_logs"
            " ORDER BY id DESC LIMIT 100")

        # Searches per minute over last 10 minutes (per-minute breakdown)
        raw_min = _analytics_execute(
            "SELECT strftime('%H:%M', created_at) as minute, COUNT(*) as count"
            " FROM search_logs WHERE created_at >= datetime('now','-10 minutes')"
            " GROUP BY minute ORDER BY minute")
        data["per_minute"] = raw_min

        data["live_clients"] = len(_SSE_CLIENTS)
        data["server_time"] = _dt.datetime.utcnow().isoformat() + "Z"

    except Exception as exc:
        data["error"] = str(exc)
    return jsonify(data)


@app.route("/admin/api/query-log")
def admin_api_query_log():
    """Paginated search log with query text, IP, device summary, and resolved location (admin only)."""
    err = _admin_check()
    if err:
        return err
    limit = min(500, max(1, request.args.get("limit", 100, type=int) or 100))
    offset = max(0, request.args.get("offset", 0, type=int) or 0)
    try:
        tot = _analytics_execute("SELECT COUNT(*) as c FROM search_logs")
        total = int(list(tot[0].values())[0]) if tot else 0
        rows = _analytics_execute(
            "SELECT id, query, search_type as type, result_count as results, latency_ms,"
            " created_at as ts, client_ip, user_agent, device_label, location"
            " FROM search_logs ORDER BY id DESC LIMIT ? OFFSET ?",
            [limit, offset],
        )
        return jsonify({
            "total": total,
            "rows": rows or [],
            "limit": limit,
            "offset": offset,
        })
    except Exception as exc:
        return jsonify({"error": str(exc), "total": 0, "rows": []}), 500


@app.route("/admin/api/account-history")
def admin_api_account_history():
    """Paginated rows from user_search_history (queries saved for logged-in accounts)."""
    err = _admin_check()
    if err:
        return err
    limit = min(500, max(1, request.args.get("limit", 100, type=int) or 100))
    offset = max(0, request.args.get("offset", 0, type=int) or 0)
    try:
        tot = _users_execute("SELECT COUNT(*) as cnt FROM user_search_history")
        total = int(tot[0]["cnt"]) if tot else 0
        rows = _users_execute(
            "SELECT h.id, h.query, h.search_type as type, h.searched_at as ts,"
            " u.id as user_id, u.username, u.email"
            " FROM user_search_history h INNER JOIN users u ON u.id = h.user_id"
            " ORDER BY h.searched_at DESC LIMIT ? OFFSET ?",
            [limit, offset],
        )
        return jsonify({
            "total": total,
            "rows": rows or [],
            "limit": limit,
            "offset": offset,
        })
    except Exception as exc:
        return jsonify({"error": str(exc), "total": 0, "rows": []}), 500


@app.route("/admin/api/stream")
def admin_api_stream():
    """Server-Sent Events endpoint — pushes live search events to admin dashboard."""
    err = _admin_check()
    if err:
        return err

    client_q: queue.Queue = queue.Queue(maxsize=200)
    with _SSE_LOCK:
        _SSE_CLIENTS.append(client_q)

    def generate():
        # Send a heartbeat immediately so browser knows connection is open
        yield "event: connected\ndata: {\"status\":\"ok\"}\n\n"
        try:
            while True:
                try:
                    data = client_q.get(timeout=25)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    # Send heartbeat every 25s to keep connection alive
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with _SSE_LOCK:
                try:
                    _SSE_CLIENTS.remove(client_q)
                except ValueError:
                    pass

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
def _build_health_payload(include_sensitive: bool = False) -> dict:
    """Build health payload for public and admin probes."""
    import datetime as _dt
    health: dict = {
        "status": "ok",
        "server_time": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "storage": _active_storage(),
        "live_sse_clients": len(_SSE_CLIENTS),
    }
    if include_sensitive and _SUPABASE_DB_URL:
        health["db_endpoint"] = _db_url_host_for_log(_SUPABASE_DB_URL)
    try:
        _analytics_execute("SELECT 1 as ok")
        health["analytics_db"] = "ok"
    except Exception as e:
        health["analytics_db"] = f"error: {e}"
        health["status"] = "degraded"
    # Test users DB
    try:
        _users_execute("SELECT 1 as ok")
        health["users_db"] = "ok"
    except Exception as e:
        health["users_db"] = f"error: {e}"
        health["status"] = "degraded"
    # Cache stats (main search TTL cache + onion status cache)
    try:
        health["cache_size"] = len(_cache)
        health["cache_maxsize"] = getattr(_cache, "maxsize", None)
        health["onion_cache_size"] = len(_onion_status_cache)
    except Exception:
        pass
    return health


@app.route("/health")
def health():
    return jsonify(_build_health_payload(include_sensitive=False))


@app.route("/admin/api/health")
def admin_api_health():
    """Health check — shows DB connectivity, cache state, live clients."""
    err = _admin_check()
    if err:
        return err
    health = _build_health_payload(include_sensitive=True)
    return jsonify(health)


# ---------------------------------------------------------------------------
# Admin AI Chatbot — knows everything about abbiey.search
# ---------------------------------------------------------------------------

_ABBIEY_SYSTEM_PROMPT = """You are the abbiey assistant, the private internal AI assistant built exclusively for the owner/admin of abbiey.search.

You are an expert in every aspect of this project. You are direct, insightful, and genuinely helpful. You think like a senior full-stack engineer and product strategist who built this system from scratch.

== ARCHITECTURE ==
- Backend: Python Flask (~4200+ lines, app.py) served as a Vercel serverless function via api/index.py
- Host: Vercel (abbieysearch.com → prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b). Deploy with: vercel deploy --prod --token <token>
- Database (priority order — _analytics_execute() routes automatically):
  1. Supabase/PostgreSQL — set SUPABASE_DB_URL env var (pooler URL port 6543). Auto-creates tables. SQL translated via _adapt_sql_pg().
  2. Turso/libSQL — set LIBSQL_URL + LIBSQL_AUTH_TOKEN env vars. SQLite-compatible HTTP API.
  3. SQLite /tmp — fallback. Ephemeral on Vercel (wiped on cold start). Fine for dev/testing.
  - analytics.db / search_logs table: query, type, region, result_count, latency_ms, hour, day_of_week, created_at
  - analytics.db / error_logs table: route, level, message, created_at
  - users.db: users, user_bookmarks, user_search_history
- Caching: TTLCache (1000 entries, 300s TTL) + threading.Lock; _in_flight dict deduplicates concurrent identical queries
- HTTP client: httpx connection pool (100 max, 20 keepalive); singleton via _get_http()
- Compression: flask-compress (Brotli preferred, gzip fallback), min_size=500 bytes
- Rate limiting: flask-limiter (30 searches/min, 5 breach-checks/min)
- Auth: Werkzeug password hashing (pbkdf2), Flask sessions
- Live dashboard: SSE /admin/api/stream pushes search events in real-time; _sse_broadcast() called from _log_search()

== SEARCH FLOW ==
1. GET /search?q=&type=&region=&lang=&df=&page=
2. Query sanitised, entities detected (detect_entities in entity_parser.py)
3. TTLCache check (key = query+type+region+page) — return instantly if hit
4. _fetch_results() dispatches by search_type:
   - "text": DDG multi-backend (DDGS lib) → DDG HTML scrape → Mojeek → DDG instant answers; multi-region fallback; entity enrichment (Wikipedia, definitions, calculations, colour previews, unit conversions)
   - "images": DDG images API
   - "news": DDG news API + feedparser RSS
   - "videos": DDG videos API
   - "code": ThreadPoolExecutor(4) → GitHub Search API + StackOverflow API + GitLab API + npm registry — ALL IN PARALLEL. Never uses DDG for code.
   - "onion": Ahmia.fi API → DDG onion-site filter fallback
5. Results deduped by URL, scored, paginated
6. _log_search() fires async (never blocks response)
7. HTML rendered via index.html (standalone, ~970 lines, does NOT extend base.html)

== KEY ROUTES ==
/ — Redirects to /search (main search UI)
/search — Search UI and results (index.html)
/login /signup /profile — Auth pages (extend base.html)
/admin?token= — THIS dashboard
/admin/analytics?token= — Legacy analytics (still works)
/admin/api/stats — JSON stats (this chatbot uses it)
/admin/api/chat — This AI endpoint
/api/user/recent-searches — Last 10 searches for logged-in user (JSON)
/opensearch.xml — OpenSearch description (add as browser default search)
/manifest.json — PWA web app manifest
/robots.txt /sitemap.xml — SEO crawlability
/breach-check — HaveIBeenPwned email checker (XposedOrNot API)

== DEPLOYMENT ==
The old deploy hook (api.vercel.com/v1/integrations/deploy/...) NEVER worked — it redeploys an old snapshot.
Correct deploy: cd /home/alex/abbiey-search-engine && /home/alex/node_modules/.bin/vercel deploy --prod --token <VERCEL_TOKEN>
GitHub: github.com/abbieymatthewslol/abbiey-search-engine (master branch)
GitHub Actions workflow: .github/workflows/deploy.yml — auto-deploys on push once VERCEL_TOKEN secret is added

== KNOWN BUGS FIXED ==
- Code search was broken (DDG results displayed in code font) — FIXED: parallel GitHub/SO/GitLab/npm fetch
- Deploy hook redeployed old snapshot — FIXED: Vercel CLI deploy
- Static files uncached (max-age=0) — FIXED: 1-year immutable cache
- Post-signup redirect to /profile standalone — FIXED: redirect to index
- DuckDuckGo-style bang redirects removed — queries like !w term are searched literally

== PERFORMANCE ==
- Cold start: ~2-3s (unavoidable on Vercel serverless)
- Cache hit: <50ms
- Typical search: 300-800ms (DDG API latency dominates)
- Compression saves ~65% on HTML payloads
- TTLCache hit rate should be >30% for healthy traffic

== GROWTH FEATURES ==
- OpenSearch XML: browsers can add as default search engine
- PWA manifest + icons: installable on mobile home screen
- Open Graph + Twitter cards: rich link previews when shared
- JSON-LD structured data: Google sitelinks search box
- Install banner: prompts users to add as browser default (dismissible, localStorage)
- Share button: Web Share API + clipboard fallback on results pages
- robots.txt + sitemap.xml: full crawler access

== HOW TO HELP IT ==
Performance: Increase TTLCache size, add Redis/Upstash for persistent cache, CDN for static assets
Growth: Submit sitemap to Google Search Console, add to browser extension directories, post on Product Hunt
Reliability: Add Sentry error tracking, health check endpoint /health, Vercel function logs
Features to build: image search results in grid, dark/light theme sync across devices, search history export, API for developers, browser extension
Monetisation: API access tiers, white-label (search is free)

Always answer as if you have full context of what's happening right now on the platform. Be specific, actionable, and opinionated. If you see data from the dashboard, analyse it and give real insights."""


@app.route("/admin/api/chat", methods=["POST"])
def admin_chat():
    """AI chatbot for the admin — specialized in abbiey.search."""
    err = _admin_check()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    user_message = (body.get("message") or "").strip()
    history = body.get("history") or []  # list of {role, content}
    dashboard_context = body.get("context") or ""  # optional JSON stats snapshot

    if not user_message:
        return jsonify({"error": "Please enter a message."}), 400

    # Build messages for LLM
    system = _ABBIEY_SYSTEM_PROMPT
    if dashboard_context:
        system += f"\n\n== CURRENT LIVE STATS (from dashboard) ==\n{dashboard_context}"

    messages = [{"role": "system", "content": system}]
    for h in history[-10:]:  # last 10 turns for context
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"][:2000]})
    messages.append({"role": "user", "content": user_message})

    # Try Ollama first (local/self-hosted)
    ollama_url = OLLAMA_BASE_URL.rstrip("/")
    try:
        resp = _get_http().post(
            f"{ollama_url}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=30,
        )
        if resp.status_code == 200:
            reply = resp.json().get("message", {}).get("content", "")
            if reply:
                return jsonify({"reply": reply, "source": "ollama"})
    except Exception:
        pass

    # Try OpenAI-compatible API if key set
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if openai_key:
        try:
            resp = _get_http().post(
                f"{openai_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}"},
                json={"model": openai_model, "messages": messages, "max_tokens": 1200},
                timeout=30,
            )
            if resp.status_code == 200:
                reply = resp.json()["choices"][0]["message"]["content"]
                return jsonify({"reply": reply, "source": "openai"})
        except Exception as exc:
            logger.warning("OpenAI chat failed: %s", exc)

    # Built-in rule-based fallback — always available
    reply = _abbiey_bot_fallback(user_message, dashboard_context)
    return jsonify({"reply": reply, "source": "builtin"})


def _abbiey_bot_fallback(msg: str, ctx: str = "") -> str:
    """Rule-based fallback when no LLM is available. Answers common admin questions."""
    m = msg.lower()

    if any(w in m for w in ["deploy", "push", "release", "live", "publish"]):
        return (
            "**Deploy command:**\n```\ncd /home/alex/abbiey-search-engine\n"
            "/home/alex/node_modules/.bin/vercel deploy --prod --token YOUR_VERCEL_TOKEN\n```\n"
            "After committing your changes, run this from the repo directory. "
            "Your Vercel token is stored securely — retrieve it from https://vercel.com/account/tokens. "
            "Takes ~60-90s. The old deploy hook on Vercel's dashboard does NOT work — always use the CLI."
        )
    if any(w in m for w in ["slow", "latency", "performance", "fast", "speed"]):
        return (
            "**Performance levers:**\n"
            "- Cache hit rate: check avg latency in stats — if >500ms consistently, TTLCache may be small\n"
            "- Cold starts: unavoidable on Vercel (~2-3s). Consider Vercel Pro for warmer instances\n"
            "- Code search: parallel fetch (GitHub/SO/GitLab/npm) — fastest path already\n"
            "- Add Upstash Redis as persistent cache layer (free tier available)\n"
            "- Enable Vercel Edge Functions for static responses"
        )
    if any(w in m for w in ["user", "signup", "register", "account"]):
        return (
            "**User system:**\n"
            "- Users stored in `users.db` (SQLite, /tmp on Vercel)\n"
            "- Auth: Werkzeug pbkdf2 hashing, Flask sessions\n"
            "- Avatar uploads: `static/avatars/` (disabled on Vercel — read-only filesystem)\n"
            "- Sessions expire when Vercel instance restarts (stateless). Consider adding a persistent session store.\n"
            "- ⚠️ SQLite in /tmp is ephemeral on Vercel — users are lost on cold starts. Migrate to Supabase or PlanetScale for production."
        )
    if any(w in m for w in ["error", "bug", "broken", "fix", "issue"]):
        return (
            "**Known fixed issues:**\n"
            "- ✅ Code search (was DDG results in code font) — now parallel GitHub/SO/GitLab/npm\n"
            "- ✅ Deploy hook (was redeploying old snapshot) — fixed with Vercel CLI\n"
            "- ✅ Static cache (max-age was 0) — now 1 year immutable\n"
            "- ✅ Post-signup redirect to /profile — now redirects to homepage\n\n"
            "**Current watch areas:**\n"
            "- SQLite in /tmp is ephemeral on Vercel (data lost on cold start)\n"
            "- Rate limiter uses in-memory storage (resets on cold start)\n"
            "- No error alerting (Sentry not yet integrated)"
        )
    if any(w in m for w in ["grow", "traffic", "seo", "users", "marketing", "promote"]):
        return (
            "**Growth actions (prioritised):**\n"
            "1. Submit sitemap to Google Search Console → https://search.google.com/search-console\n"
            "2. Submit to Bing Webmaster Tools\n"
            "3. Post on ProductHunt (best day: Tuesday)\n"
            "4. Submit to browser extension stores (Chrome, Firefox) as default search option\n"
            "5. OpenSearch is live — users who visit can add via browser address bar\n"
            "6. Share button on results → viral loop\n"
            "7. Reddit posts in r/privacy, r/degoogle, r/selfhosted\n"
            "8. Add to alternativeto.net as DuckDuckGo/Google alternative"
        )
    if any(w in m for w in ["search", "ddg", "duckduckgo", "result"]):
        return (
            "**Search architecture:**\n"
            "- Primary: DDGS library (DuckDuckGo) with multi-backend fallback\n"
            "- Code: GitHub API + StackOverflow + GitLab + npm (parallel, never DDG)\n"
            "- Images/News/Videos: DDG-specific APIs\n"
            "- Onion: Ahmia.fi → DDG onion fallback\n"
            "- Entity enrichment: Wikipedia, definitions, calculations, colour, units\n"
            "- Cache: TTLCache 1000 entries, 300s TTL\n"
            "- Search operators: site:, filetype:, before:, after:, etc."
        )
    if any(w in m for w in ["database", "sqlite", "db", "storage", "data"]):
        return (
            "**Data storage:**\n"
            "- `analytics.db` → search_logs, error_logs (grows ~1KB per 10 searches)\n"
            "- `users.db` → users table\n"
            "⚠️ All SQLite files live in `/tmp` on Vercel — **ephemeral, wiped on cold start**.\n"
            "For production persistence, migrate to: Turso (SQLite-compatible), Supabase (PostgreSQL), or PlanetScale."
        )
    if any(w in m for w in ["feature", "next", "todo", "build", "add", "improve"]):
        return (
            "**High-impact features to build next:**\n"
            "1. **Persistent database** (Turso/Supabase) — most critical, analytics are lost on restart\n"
            "2. **Browser extension** — install as default search from Chrome/Firefox store\n"
            "3. **Search result clustering** — group results by topic/source\n"
            "4. **API endpoint** — `GET /api/search?q=&key=` for developers\n"
            "5. **Saved searches / bookmarks** — user collections\n"
            "6. **Custom themes** — beyond dark/light\n"
            "7. **Search suggestions** — live autocomplete as you type\n"
            "8. **PDF/document search** — specialized tab\n"
            "9. **Answer engine mode** — AI-summarised answers at top\n"
            "10. **Sentry error tracking** — get alerts on production errors"
    # Generic helpful response
        )
    return (
        f"I'm the abbiey assistant — I know how abbiey.search is built and run. Ask me about:\n"
        "- **Deploy** — how to push changes live\n"
        "- **Performance** — latency, caching, cold starts\n"
        "- **Search** — how DDG/code/onion search works\n"
        "- **Users** — auth, sessions, database\n"
        "- **Growth** — SEO, traffic, marketing\n"
        "- **Errors** — known bugs, fixes, monitoring\n"
        "- **Features** — what to build next\n\n"
        "For full AI responses, set `OLLAMA_BASE_URL` (local Ollama) or `OPENAI_API_KEY` in Vercel environment variables."
# ---------------------------------------------------------------------------
# Fallback infrastructure — every query MUST return results
# ---------------------------------------------------------------------------

# ---- Layer 1: DDG multi-backend ----
    )

def _try_ddg(query, max_results, search_type, region=None, time_filter=None, safesearch="off"):
    """Primary: ddgs library with all backends enabled."""
    ddg = DDGS()
    kwargs = {"safesearch": safesearch or "off"}
    if region:
        kwargs["region"] = region

    if search_type == "images":
        raw = list(ddg.images(query, max_results=max_results, **kwargs))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "image": r.get("image", ""),
                "thumbnail": r.get("thumbnail", ""),
                "source": r.get("source", ""),
            }
            for r in raw
        ]
    elif search_type == "news":
        if time_filter and time_filter in {"d", "w", "m", "y"}:
            kwargs["timelimit"] = time_filter
        raw = list(ddg.news(query, max_results=max_results, **kwargs))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "body": r.get("body", ""),
                "source": r.get("source", ""),
                "date": r.get("date", ""),
            }
            for r in raw
        ]
    elif search_type == "videos":
        raw = list(ddg.videos(query, max_results=max_results, **kwargs))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("content", ""),
                "description": r.get("description", ""),
                "publisher": r.get("publisher", ""),
                "thumbnail": r.get("images", {}).get("large", "")
                if isinstance(r.get("images"), dict)
                else "",
                "duration": r.get("duration", ""),
            }
            for r in raw
        ]
    else:
        if time_filter and time_filter in {"d", "w", "m", "y"}:
            kwargs["timelimit"] = time_filter
        raw = list(ddg.text(
            query,
            max_results=max_results,
            **kwargs,
        ))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "body": r.get("body", ""),
            }
            for r in raw
        ]


# ---- Layer 2: Wikipedia / MediaWiki API (text only) ----

def _try_wikipedia(query, lang=None):
    """Query Wikipedia's opensearch + extracts API."""
    wiki_lang = lang or "en"
    base = f"https://{wiki_lang}.wikipedia.org/w/api.php"
    results = []
    try:
        resp = _get_http().get(
            base,
            params={
                "action": "opensearch",
                "search": query,
                "limit": "10",
                "namespace": "0",
                "format": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) >= 4:
            titles = data[1] or []
            descriptions = data[2] or []
            urls = data[3] or []
            for i in range(len(titles)):
                results.append({
                    "title": titles[i] if i < len(titles) else "",
                    "url": urls[i] if i < len(urls) else "",
                    "body": descriptions[i] if i < len(descriptions) else "",
                })

        needs_extract = [r for r in results if not r["body"] and r["title"]]
        if needs_extract:
            titles_param = "|".join(r["title"] for r in needs_extract[:5])
            resp2 = _get_http().get(
                base,
                params={
                    "action": "query",
                    "titles": titles_param,
                    "prop": "extracts",
                    "exintro": "1",
                    "explaintext": "1",
                    "exsentences": "3",
                    "format": "json",
                },
            )
            resp2.raise_for_status()
            pages = resp2.json().get("query", {}).get("pages", {})
            extract_map = {}
            for page in pages.values():
                if "extract" in page:
                    extract_map[page.get("title", "")] = page["extract"]
            for r in results:
                if not r["body"] and r["title"] in extract_map:
                    r["body"] = extract_map[r["title"]]

        if results:
            logger.info("Wikipedia fallback: %d results", len(results))
    except Exception:
        logger.warning("Wikipedia fallback failed", exc_info=True)

    return results


# ---- Layer 4: Wiby.me (indie/small web search, text only) ----

def _try_wiby(query):
    """Search the indie/small web via Wiby.me JSON API."""
    results = []
    try:
        resp = _get_http().get(
            "https://wiby.me/json/",
            params={"q": query},
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data if isinstance(data, list) else data.get("results", [])
        for r in raw:
            url = r.get("URL", r.get("url", ""))
            title = r.get("Title", r.get("title", url))
            snippet = r.get("Snippet", r.get("snippet", ""))
            if url:
                results.append({"title": title, "url": url, "body": snippet})
        if results:
            logger.info("Wiby.me fallback: %d results", len(results))
    except Exception:
        logger.warning("Wiby.me fallback failed", exc_info=True)
    return results


# ---- Layer 5: Mojeek direct HTML fallback (text only) ----

def _try_mojeek(query):
    """Scrape Mojeek search results as a deep fallback."""
    results = []
    try:
        resp = _get_http().get(
            "https://www.mojeek.com/search",
            params={"q": query},
            headers={"User-Agent": "abbiey.search/1.0"},
        )
        resp.raise_for_status()
        html = resp.text
        links = re.findall(
            r'<a[^>]*class="title"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.DOTALL,
        )
        if not links:
            # Fallback: href before class
            links = re.findall(
                r'<a[^>]*href="([^"]+)"[^>]*class="title"[^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            )
        snippets = re.findall(r'<p class="s">(.*?)</p>', html, re.DOTALL)
        for i, (url, title) in enumerate(links):
            clean_title = re.sub(r"<[^>]+>", "", title).strip()
            clean_body = ""
            if i < len(snippets):
                clean_body = re.sub(r"<[^>]+>", "", snippets[i]).strip()
            if url:
                results.append({
                    "title": clean_title,
                    "url": url,
                    "body": clean_body,
                })
        if results:
            logger.info("Mojeek fallback: %d results", len(results))
    except Exception:
        logger.warning("Mojeek fallback failed", exc_info=True)
    return results


# ---- Layer 6: DDG instant answers + suggestions (last resort, text only) ----

def _try_ddg_instant(query):
    """Use DDG's instant answer API and suggestions."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1"},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("AbstractText") and data.get("AbstractURL"):
            results.append({
                "title": data.get("Heading", query),
                "url": data["AbstractURL"],
                "body": data["AbstractText"],
            })

        for topic in data.get("RelatedTopics", []):
            if isinstance(topic, dict):
                if "FirstURL" in topic and "Text" in topic:
                    results.append({
                        "title": topic.get("Text", "")[:120],
                        "url": topic["FirstURL"],
                        "body": topic.get("Text", ""),
                    })
                for sub in topic.get("Topics", []):
                    if isinstance(sub, dict) and "FirstURL" in sub:
                        results.append({
                            "title": sub.get("Text", "")[:120],
                            "url": sub["FirstURL"],
                            "body": sub.get("Text", ""),
                        })

        for r in data.get("Results", []):
            if isinstance(r, dict) and r.get("FirstURL"):
                results.append({
                    "title": r.get("Text", "")[:120],
                    "url": r["FirstURL"],
                    "body": r.get("Text", ""),
                })

        if results:
            logger.info("DDG instant answer fallback: %d results", len(results))
    except Exception:
        logger.warning("DDG instant answer fallback failed", exc_info=True)

    try:
        ac_resp = _get_http().get(
            "https://duckduckgo.com/ac/",
            params={"q": query, "type": "list"},
        )
        ac_resp.raise_for_status()
        ac_data = ac_resp.json()
        phrases = []
        if isinstance(ac_data, list) and len(ac_data) > 1 and isinstance(ac_data[1], list):
            phrases = ac_data[1][:6]
        elif isinstance(ac_data, list) and ac_data and isinstance(ac_data[0], dict):
            phrases = [item["phrase"] for item in ac_data[:6] if "phrase" in item]
        for phrase in phrases:
            if phrase and phrase.lower() != query.lower():
                results.append({
                    "title": f"Related search: {phrase}",
                    "url": f"https://duckduckgo.com/?q={phrase.replace(' ', '+')}",
                    "body": f'Try searching for "{phrase}" for more results.',
                })
    except Exception:
        pass

    return results


# ---- Inclusive search: no one lands on a totally blank page ----

_CRISIS_QUERY_RE = re.compile(
    r"(?i)\b("
    r"suicide|suicidal|kill\s*my\s*self|killing\s*my\s*self|end\s*my\s*life|want\s*to\s*die|"
    r"don'?t\s*want\s*to\s*live|better\s*off\s*dead|no\s*reason\s*to\s*live|"
    r"self[\s-]*harm|hurt\s*my\s*self|cut\s*my\s*self|"
    r"over\s*dose|overdose|"
    r"can'?t\s*go\s*on|cannot\s*go\s*on|end\s*it\s*all|"
    r"wish\s*i\s*(was|were)\s*dead"
    r")\b",
)


def _query_looks_chaotic(q: str) -> bool:
    """Very long, symbol-heavy, or frantic punctuation — indexes may struggle; still deserves help."""
    s = (q or "").strip()
    if len(s) > 320:
        return True
    if len(s) < 12:
        return False
    alnum = sum(1 for c in s if c.isalnum())
    if len(s) >= 48 and alnum / len(s) < 0.32:
        return True
    if s.count("?") >= 6 or s.count("!") >= 8:
        return True
    return False


def search_safeguard_meta(raw_query: str) -> dict:
    """UI hints + optional crisis strip. Does not block or alter the query."""
    q = (raw_query or "").strip()
    crisis = bool(_CRISIS_QUERY_RE.search(q))
    chaotic = _query_looks_chaotic(q)
    return {
        "show_crisis_strip": crisis,
        "show_inclusive_hint": crisis or chaotic,
        "chaotic_query": chaotic,
    }


def _simplify_query_for_fallback(q: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (q or ""), flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split()[:16]
    return " ".join(words)


def _static_search_portal_links(q: str) -> list:
    """Curated outbound searches so the SERP is never completely empty."""
    enc = quote_plus((q or "information")[:280])
    base = (os.environ.get("SITE_URL") or "https://abbieysearch.com").rstrip("/")
    return [
        {
            "title": "DuckDuckGo — open full web results",
            "url": f"https://duckduckgo.com/?q={enc}",
            "body": "Same query in a broad web index (off-site).",
            "source": "Search portal",
        },
        {
            "title": "Wikipedia — article search",
            "url": f"https://en.wikipedia.org/w/index.php?search={enc}&title=Special%3ASearch",
            "body": "Encyclopedia pages and disambiguation for your words.",
            "source": "Search portal",
        },
        {
            "title": "Internet Archive — archived pages",
            "url": f"https://archive.org/search?query={enc}",
            "body": "Billions of archived URLs; strong for older or niche material.",
            "source": "Search portal",
        },
        {
            "title": "abbiey.search — access & alternatives (JSON)",
            "url": f"{base}/api/access-resources",
            "body": "Tor, archives, independent indexes, and tips if one backend is empty.",
            "source": "Search portal",
        },
    ]


def _inclusive_text_recovery_bridge(
    backend_query: str,
    lang,
    region,
    time_filter,
    safesearch,
    raw_query: str | None = None,
    max_hits: int = 22,
) -> list:
    """
    After normal text fallbacks still return nothing: milder queries + portals.
    Never judges the user; only adds more retrieval paths.
    """
    raw = (raw_query or backend_query or "").strip()
    bq = (backend_query or raw).strip()
    if not raw and not bq:
        return _static_search_portal_links("")

    seen: set[str] = set()
    out: list = []

    def _take(batch):
        nonlocal out
        for r in batch or []:
            u = (r.get("url") or "").strip()
            if not u or u in seen:
                continue
            seen.add(u)
            out.append(r)
            if len(out) >= max_hits:
                return True
        return False

    variants = []
    for cand in (bq, raw):
        c = (cand or "").strip()
        if c and c not in variants:
            variants.append(c)
    simp = _simplify_query_for_fallback(raw)
    if simp and simp.lower() not in {v.lower() for v in variants}:
        variants.append(simp)
    head = " ".join(raw.split()[:10]).strip()
    if head and head.lower() not in {v.lower() for v in variants}:
        variants.append(head)

    for v in variants:
        try:
            if _take(_try_ddg(v, min(24, max_hits), "text", region, time_filter, safesearch)):
                logger.info("inclusive_recovery: DDG ok for variant len=%s", len(v))
                return out
        except Exception:
            logger.debug("inclusive_recovery_ddg_failed", exc_info=True)

    for v in variants[:3]:
        try:
            if _take(_try_wikipedia(v, lang)):
                logger.info("inclusive_recovery: Wikipedia ok")
                return out
        except Exception:
            logger.debug("inclusive_recovery_wiki_failed", exc_info=True)

    try:
        if _take(_try_wiby(simp or bq or raw)):
            logger.info("inclusive_recovery: Wiby ok")
            return out
    except Exception:
        logger.debug("inclusive_recovery_wiby_failed", exc_info=True)

    _take(_static_search_portal_links(raw or bq))
    return out[:max_hits]


# ---- Image fallback layers ----

def _try_openverse(query, max_results=20, filters=None):
    """Search Openverse (open catalogue, CC licenses). Optional filters: license, license_type, aspect_ratio, size, extension."""
    filters = filters or {}
    results = []
    try:
        params = {
            "q": query,
            "page_size": min(max(int(max_results or 20), 1), 50),
            "page": 1,
        }
        for src_key, api_key in (
            ("license", "license"),
            ("license_type", "license_type"),
            ("aspect_ratio", "aspect_ratio"),
            ("size", "size"),
            ("extension", "extension"),
        ):
            v = filters.get(src_key)
            if v:
                params[api_key] = v
        resp = _get_http().get(
            "https://api.openverse.org/v1/images/",
            params=params,
            headers={"User-Agent": "abbiey.search/1.0", "Accept": "application/json"},
            timeout=12.0,
        )
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
            lic = r.get("license") or ""
            prov = r.get("provider") or r.get("source") or "openverse"
            results.append({
                "title": r.get("title", ""),
                "url": r.get("foreign_landing_url", r.get("url", "")),
                "image": r.get("url", ""),
                "thumbnail": r.get("thumbnail", r.get("url", "")),
                "source": f"Openverse · {prov}" if prov else "Openverse",
                "license": lic,
                "attribution": (r.get("attribution") or "")[:280],
            })
        if results:
            logger.info("Openverse: %d image results (filters=%s)", len(results), bool(filters))
    except Exception:
        logger.warning("Openverse image search failed", exc_info=True)
    return results


def _norm_image_dedupe_key(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
        return f"{p.netloc.lower()}{p.path.lower()}"[:800]
    except Exception:
        return url.strip().lower()[:400]


def _interleave_image_buckets(buckets: dict, order: list) -> list:
    """Round-robin merge; dedupe by image / landing URL."""
    seen = set()
    out = []
    max_len = max((len(buckets.get(k, [])) for k in order), default=0)
    for i in range(max_len):
        for k in order:
            row_list = buckets.get(k) or []
            if i >= len(row_list):
                continue
            r = row_list[i]
            key = _norm_image_dedupe_key(r.get("image") or r.get("thumbnail") or "")
            if not key:
                key = _norm_image_dedupe_key(r.get("url") or "")
            if key:
                if key in seen:
                    continue
                seen.add(key)
            out.append(r)
    return out


def _fetch_images_multi_source(
    query: str,
    max_results: int,
    region,
    time_filter,
    safesearch: str,
    opts: dict,
) -> list:
    """Blend DuckDuckGo with open catalogues (Openverse, Wikimedia Commons, Internet Archive)."""
    sources = list(opts.get("sources") or ["ddg", "openverse", "commons"])
    allowed = {"ddg", "openverse", "commons", "archive"}
    sources = [s for s in sources if s in allowed]
    if not sources:
        sources = ["ddg", "openverse", "commons"]

    ov_filters = {}
    if opts.get("license"):
        ov_filters["license"] = opts["license"]
    if opts.get("license_type"):
        ov_filters["license_type"] = opts["license_type"]
    if opts.get("aspect"):
        ov_filters["aspect_ratio"] = opts["aspect"]
    if opts.get("size"):
        ov_filters["size"] = opts["size"]
    if opts.get("extension"):
        ov_filters["extension"] = opts["extension"]

    buckets = {k: [] for k in allowed}
    with ThreadPoolExecutor(max_workers=4) as _pool:
        futs = {}
        if "ddg" in sources:
            futs["ddg"] = _pool.submit(
                _try_ddg, query, max_results, "images", region, time_filter, safesearch
            )
        if "openverse" in sources:
            futs["openverse"] = _pool.submit(_try_openverse, query, min(40, max_results), ov_filters)
        if "commons" in sources:
            futs["commons"] = _pool.submit(_try_wikimedia_commons, query)
        if "archive" in sources:
            futs["archive"] = _pool.submit(_try_internet_archive_images, query, max_results)
        for name, fut in futs.items():
            try:
                buckets[name] = fut.result(timeout=12) or []
            except Exception:
                logger.warning("multi-source images: %s failed", name, exc_info=True)
                buckets[name] = []

    order = [k for k in ("ddg", "openverse", "commons", "archive") if k in sources]
    merged = _interleave_image_buckets(buckets, order)
    if not merged:
        try:
            merged = _try_ddg(query, max_results, "images", region, time_filter, safesearch) or []
        except Exception:
            merged = []
    return merged


def _parse_image_search_options():
    """Parse ?img_adv=1 and Openverse-compatible filters from the query string."""
    if not has_request_context():
        return None
    flag = request.args.get("img_adv", "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return None

    lic = request.args.get("img_license", "").strip().lower()
    if lic not in {"", "cc0", "pdm", "by", "by-sa", "by-nc", "by-nc-sa", "by-nd", "by-nc-nd"}:
        lic = ""

    lt = request.args.get("img_license_type", "").strip().lower()
    if lt not in {"", "commercial", "modification"}:
        lt = ""

    aspect = request.args.get("img_aspect", "").strip().lower()
    if aspect not in {"", "tall", "wide", "square"}:
        aspect = ""

    size = request.args.get("img_size", "").strip().lower()
    if size not in {"", "small", "medium", "large"}:
        size = ""

    ext = request.args.get("img_ext", "").strip().lower()
    if ext == "jpeg":
        ext = "jpg"
    if ext not in {"", "jpg", "png", "gif", "svg", "webp"}:
        ext = ""

    allow = {"ddg", "openverse", "commons", "archive"}
    src_list = request.args.getlist("img_src")
    if src_list:
        sources = [p.strip().lower() for p in src_list if p.strip().lower() in allow]
    else:
        raw_src = request.args.get("img_src", "ddg,openverse,commons").strip().lower()
        parts = [p.strip() for p in raw_src.split(",") if p.strip()]
        sources = [p for p in parts if p in allow]
    if not sources:
        sources = ["ddg", "openverse", "commons"]

    return {
        "license": lic,
        "license_type": lt,
        "aspect": aspect,
        "size": size,
        "extension": ext,
        "sources": sources,
    }


def _image_search_url_extras(opts: dict | None) -> str:
    """Query string fragment (no leading ?) for links & infinite scroll."""
    if not opts:
        return ""
    pairs = [("img_adv", "1")]
    if opts.get("license"):
        pairs.append(("img_license", opts["license"]))
    if opts.get("license_type"):
        pairs.append(("img_license_type", opts["license_type"]))
    if opts.get("aspect"):
        pairs.append(("img_aspect", opts["aspect"]))
    if opts.get("size"):
        pairs.append(("img_size", opts["size"]))
    if opts.get("extension"):
        pairs.append(("img_ext", opts["extension"]))
    for s in opts.get("sources") or []:
        pairs.append(("img_src", s))
    return urlencode(pairs, doseq=True)


def _try_wikimedia_commons(query):
    """Search Wikimedia Commons for images."""
    results = []
    try:
        resp = _get_http().get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": "20",
                "gsrnamespace": "6",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": "300",
                "format": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            ii = page.get("imageinfo", [{}])[0]
            title = page.get("title", "").replace("File:", "")
            if ii.get("url"):
                results.append({
                    "title": title,
                    "url": ii.get("descriptionurl", ii.get("url", "")),
                    "image": ii.get("url", ""),
                    "thumbnail": ii.get("thumburl", ii.get("url", "")),
                    "source": "Wikimedia Commons",
                })
        if results:
            logger.info("Wikimedia Commons fallback: %d image results", len(results))
    except Exception:
        logger.warning("Wikimedia Commons fallback failed", exc_info=True)
    return results


def _try_internet_archive_images(query, max_results=30):
    """Search Internet Archive for public domain images (no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": f"({query}) AND mediatype:image",
                "output": "json",
                "rows": min(max_results, 50),
                "fl[]": ["identifier", "title", "description"],
                "sort[]": "downloads desc",
            },
        )
        resp.raise_for_status()
        for doc in resp.json().get("response", {}).get("docs", []):
            identifier = doc.get("identifier", "")
            if not identifier:
                continue
            title = doc.get("title", identifier)
            if isinstance(title, list):
                title = title[0] if title else identifier
            results.append({
                "title": title,
                "url": f"https://archive.org/details/{identifier}",
                "image": f"https://archive.org/services/img/{identifier}",
                "thumbnail": f"https://archive.org/services/img/{identifier}",
                "source": "Internet Archive",
            })
        if results:
            logger.info("Internet Archive images: %d results", len(results))
    except Exception:
        logger.warning("Internet Archive images failed", exc_info=True)
    return results


# ---- News fallback layer ----

def _try_google_news_rss(query):
    """Parse Google News RSS feed for news results."""
    results = []
    try:
        encoded = quote_plus(query)
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        )
        for entry in feed.entries[:20]:
            source_title = "Google News"
            if hasattr(entry, "source") and hasattr(entry.source, "title"):
                source_title = entry.source.title
            results.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "body": re.sub(r"<[^>]+>", "", entry.get("summary", "")),
                "source": source_title,
                "date": entry.get("published", ""),
            })
        if results:
            logger.info("Google News RSS fallback: %d results", len(results))
    except Exception:
        logger.warning("Google News RSS fallback failed", exc_info=True)
    return results


def _try_bing_news_rss(query):
    """Parse Bing News RSS feed for news results (no key required)."""
    results = []
    try:
        encoded = quote_plus(query)
        feed = feedparser.parse(
            f"https://www.bing.com/news/search?q={encoded}&format=rss",
            request_headers={"User-Agent": "Mozilla/5.0 (compatible; abbiey.search/1.0)"},
        )
        for entry in feed.entries[:20]:
            source_title = getattr(getattr(entry, "source", None), "title", None) or "Bing News"
            results.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "body": re.sub(r"<[^>]+>", "", entry.get("summary", "")),
                "source": source_title,
                "date": entry.get("published", ""),
            })
        if results:
            logger.info("Bing News RSS fallback: %d results", len(results))
    except Exception:
        logger.warning("Bing News RSS fallback failed", exc_info=True)
    return results


def _try_hackernews(query, max_results=20):
    """Search Hacker News via Algolia API (free, no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": min(max_results, 30)},
        )
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            title = hit.get("title", "")
            if not title or not url:
                continue
            points = hit.get("points") or 0
            author = hit.get("author", "")
            created_at = (hit.get("created_at") or "")[:10]
            body = f"{points} points · {author}"
            if created_at:
                body += f" · {created_at}"
            results.append({
                "title": title,
                "url": url,
                "body": body,
                "source": "Hacker News",
                "date": created_at,
            })
        if results:
            logger.info("HackerNews Algolia: %d results", len(results))
    except Exception:
        logger.warning("HackerNews search failed", exc_info=True)
    return results


def _try_reddit_news(query, max_results=20):
    """Search Reddit for relevant posts via public JSON API (no key required)."""
    import datetime as _dt
    results = []
    try:
        resp = _get_http().get(
            "https://www.reddit.com/search.json",
            params={"q": query, "sort": "relevance", "t": "month",
                    "limit": min(max_results, 25), "type": "link"},
            headers={"User-Agent": "abbiey.search/1.0 (privacy search engine)"},
        )
        resp.raise_for_status()
        for child in resp.json().get("data", {}).get("children", []):
            post = child.get("data", {})
            url = post.get("url", "")
            title = post.get("title", "")
            if not url or not title:
                continue
            score = post.get("score", 0)
            sub = post.get("subreddit_name_prefixed", "")
            created = post.get("created_utc", 0)
            date_str = ""
            if created:
                date_str = _dt.datetime.fromtimestamp(
                    created, tz=_dt.timezone.utc
                ).strftime("%Y-%m-%d")
            results.append({
                "title": title,
                "url": url,
                "body": f"{sub} · {score} upvotes",
                "source": f"Reddit",
                "date": date_str,
            })
        if results:
            logger.info("Reddit news: %d results", len(results))
    except Exception:
        logger.warning("Reddit news search failed", exc_info=True)
    return results


# ---- Code search layers ----

def _try_github_search(query, max_results=30):
    """Search GitHub repositories and code via the search API (no auth needed for basic)."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "per_page": min(max_results, 30)},
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        resp.raise_for_status()
        for r in resp.json().get("items", []):
            lang = r.get("language", "")
            stars = r.get("stargazers_count", 0)
            stars_str = f"{stars:,}" if stars < 10000 else f"{stars/1000:.1f}k"
            results.append({
                "title": r.get("full_name", ""),
                "url": r.get("html_url", ""),
                "body": r.get("description", "") or "",
                "language": lang or "",
                "stars": stars_str,
                "forks": str(r.get("forks_count", 0)),
                "source": "GitHub",
            })
        if results:
            logger.info("GitHub search: %d results", len(results))
    except Exception:
        logger.warning("GitHub search failed", exc_info=True)
    return results


def _try_stackoverflow(query, max_results=20):
    """Search StackOverflow questions via API (no auth needed)."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.stackexchange.com/2.3/search/excerpts",
            params={
                "order": "desc", "sort": "relevance",
                "q": query, "site": "stackoverflow",
                "pagesize": min(max_results, 20),
                "filter": "default",
            },
        )
        resp.raise_for_status()
        for r in resp.json().get("items", []):
            q_id = r.get("question_id", "")
            title = re.sub(r"<[^>]+>", "", r.get("title", ""))
            body = re.sub(r"<[^>]+>", "", r.get("excerpt", ""))
            tags = r.get("tags", [])
            results.append({
                "title": title,
                "url": f"https://stackoverflow.com/q/{q_id}",
                "body": body,
                "language": tags[0] if tags else "",
                "stars": str(r.get("score", 0)),
                "forks": "",
                "source": "StackOverflow",
                "tags": tags[:4],
            })
        if results:
            logger.info("StackOverflow search: %d results", len(results))
    except Exception:
        logger.warning("StackOverflow search failed", exc_info=True)
    return results


def _try_code_ddg(query, max_results=50):
    """Search for code using DDG with code-focused query modifiers."""
    try:
        code_query = f"{query} site:github.com OR site:stackoverflow.com OR site:gitlab.com"
        return _try_ddg(code_query, max_results, "text")
    except Exception:
        return []


def _try_gitlab(query, max_results=20):
    """Search GitLab.com public repositories (unauthenticated, no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://gitlab.com/api/v4/projects",
            params={"search": query, "per_page": min(max_results, 20),
                    "order_by": "last_activity_at", "sort": "desc"},
        )
        resp.raise_for_status()
        for r in resp.json():
            stars = r.get("star_count", 0)
            stars_str = f"{stars:,}" if stars < 10000 else f"{stars/1000:.1f}k"
            lang = r.get("predominant_language") or ""
            results.append({
                "title": r.get("path_with_namespace", r.get("name", "")),
                "url": r.get("web_url", ""),
                "body": r.get("description", "") or "",
                "language": lang,
                "stars": stars_str,
                "forks": str(r.get("forks_count", 0)),
                "source": "GitLab",
            })
        if results:
            logger.info("GitLab search: %d results", len(results))
    except Exception:
        logger.warning("GitLab search failed", exc_info=True)
    return results


def _try_npm(query, max_results=20):
    """Search npm registry for packages (free, no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://registry.npmjs.org/-/v1/search",
            params={"text": query, "size": min(max_results, 20)},
        )
        resp.raise_for_status()
        for obj in resp.json().get("objects", []):
            pkg = obj.get("package", {})
            name = pkg.get("name", "")
            desc = pkg.get("description", "")
            npm_url = pkg.get("links", {}).get("npm", f"https://www.npmjs.com/package/{name}")
            keywords = pkg.get("keywords", [])[:4]
            version = pkg.get("version", "")
            body = f"v{version} · {desc}" if version and desc else (desc or f"v{version}")
            results.append({
                "title": name,
                "url": npm_url,
                "body": body,
                "language": "JavaScript",
                "stars": "",
                "forks": "",
                "source": "npm",
                "tags": keywords,
            })
        if results:
            logger.info("npm search: %d results", len(results))
    except Exception:
        logger.warning("npm search failed", exc_info=True)
    return results


def _try_marginalia(query):
    """Search Marginalia indie/alternative web engine (free, no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://search.marginalia.nu/api/search",
            params={"query": query},
            timeout=5.0,
        )
        for r in resp.json().get("results", []):
            url = r.get("url", "")
            if not url:
                continue
            results.append({
                "title": r.get("title", "") or url,
                "url": url,
                "body": r.get("description", ""),
            })
        if results:
            logger.info("Marginalia: %d results", len(results))
    except Exception:
        logger.warning("Marginalia search failed", exc_info=True)
    return results


def _try_internet_archive_videos(query, max_results=20):
    """Search Internet Archive for public domain / CC-licensed videos (no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": f"({query}) AND mediatype:movies",
                "output": "json",
                "rows": min(max_results, 50),
                "fl[]": ["identifier", "title", "description", "creator"],
                "sort[]": "downloads desc",
            },
        )
        resp.raise_for_status()
        for doc in resp.json().get("response", {}).get("docs", []):
            identifier = doc.get("identifier", "")
            if not identifier:
                continue
            title = doc.get("title", identifier)
            if isinstance(title, list):
                title = title[0] if title else identifier
            desc = doc.get("description", "")
            if isinstance(desc, list):
                desc = desc[0] if desc else ""
            creator = doc.get("creator", "")
            if isinstance(creator, list):
                creator = creator[0] if creator else ""
            results.append({
                "title": title,
                "url": f"https://archive.org/details/{identifier}",
                "description": (desc or "")[:200],
                "publisher": creator or "Internet Archive",
                "thumbnail": f"https://archive.org/services/img/{identifier}",
                "duration": "",
            })
        if results:
            logger.info("Internet Archive videos: %d results", len(results))
    except Exception:
        logger.warning("Internet Archive videos failed", exc_info=True)
    return results


_PEERTUBE_INSTANCES = [
    "https://framatube.org",
    "https://peertube.social",
]


def _try_peertube(query, max_results=20):
    """Search PeerTube federated video network via public instances (no key required)."""
    results = []
    for instance in _PEERTUBE_INSTANCES:
        try:
            resp = _get_http().get(
                f"{instance}/api/v1/search/videos",
                params={"search": query, "count": min(max_results, 20), "sort": "-match"},
                timeout=5.0,
            )
            if resp.status_code != 200:
                continue
            for v in resp.json().get("data", []):
                thumb = v.get("thumbnailPath", "")
                thumb_url = f"{instance}{thumb}" if thumb.startswith("/") else thumb
                channel = (v.get("channel") or {}).get("displayName", "") or \
                          (v.get("account") or {}).get("displayName", "")
                results.append({
                    "title": v.get("name", ""),
                    "url": v.get("url", "") or f"{instance}/w/{v.get('uuid', '')}",
                    "description": (v.get("description") or "")[:200],
                    "publisher": channel or instance,
                    "thumbnail": thumb_url,
                    "duration": str(v.get("duration", "")),
                })
            if results:
                logger.info("PeerTube (%s): %d results", instance, len(results))
                break
        except Exception:
            logger.warning("PeerTube instance %s failed", instance, exc_info=True)
    return results


# ---- Additional deep knowledge sources ----

_ACADEMIC_TERMS = frozenset({
    "research", "paper", "study", "journal", "academic", "review", "analysis",
    "theory", "algorithm", "method", "model", "experiment", "clinical", "medical",
    "science", "university", "arxiv", "doi", "preprint", "physics", "chemistry",
    "biology", "mathematics", "statistics", "engineering", "cognitive", "neural",
    "machine learning", "deep learning", "quantum", "genomics", "neuroscience",
    "psychology", "sociology", "economics", "epidemiology", "pathology", "genome",
    "protein", "molecule", "catalyst", "theorem", "hypothesis", "meta-analysis",
})


def _looks_academic(query: str) -> bool:
    q = query.lower()
    return any(term in q for term in _ACADEMIC_TERMS)


def _try_arxiv(query, max_results=10):
    """Search arXiv preprints/academic papers (free API, no key required)."""
    import xml.etree.ElementTree as ET
    results = []
    try:
        resp = _get_http().get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": min(max_results, 20),
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
            timeout=6.0,
        )
        resp.raise_for_status()
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            id_el = entry.find("atom:id", ns)
            authors = [
                a.find("atom:name", ns).text
                for a in entry.findall("atom:author", ns)
                if a.find("atom:name", ns) is not None
            ]
            if not title_el or not id_el:
                continue
            title = re.sub(r"\s+", " ", title_el.text or "").strip()
            summary = re.sub(r"\s+", " ", summary_el.text or "").strip()[:400] if summary_el else ""
            url = (id_el.text or "").strip().replace("http://", "https://")
            author_str = ", ".join(authors[:3])
            if author_str:
                summary = f"{author_str} — {summary}" if summary else author_str
            results.append({
                "title": title,
                "url": url,
                "body": summary,
                "source": "arXiv",
                "source_type": "academic",
            })
        if results:
            logger.info("arXiv: %d results", len(results))
    except Exception:
        logger.warning("arXiv search failed", exc_info=True)
    return results


def _try_pubmed(query, max_results=8):
    """Search PubMed via NCBI E-utilities (free, no key required)."""
    results = []
    try:
        search_resp = _get_http().get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": min(max_results, 20),
                "retmode": "json",
                "sort": "relevance",
            },
            timeout=5.0,
        )
        search_resp.raise_for_status()
        ids = search_resp.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return results
        summary_resp = _get_http().get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids[:10]), "retmode": "json"},
            timeout=5.0,
        )
        summary_resp.raise_for_status()
        doc_data = summary_resp.json().get("result", {})
        for uid in doc_data.get("uids", []):
            doc = doc_data.get(uid, {})
            title = doc.get("title", "")
            if not title:
                continue
            source = doc.get("source", "")
            pubdate = doc.get("pubdate", "")
            authors = doc.get("authors", [])
            author_str = ", ".join(a.get("name", "") for a in authors[:2])
            body = " · ".join(filter(None, [author_str, source, pubdate]))
            results.append({
                "title": title,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                "body": body,
                "source": "PubMed",
                "source_type": "academic",
            })
        if results:
            logger.info("PubMed: %d results", len(results))
    except Exception:
        logger.warning("PubMed search failed", exc_info=True)
    return results


def _try_crossref(query, max_results=8):
    """Search Crossref for academic papers by DOI/metadata (free, no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.crossref.org/works",
            params={
                "query": query,
                "rows": min(max_results, 20),
                "select": "DOI,title,abstract,author,published-print,published-online,container-title",
            },
            headers={"User-Agent": "abbiey.search/1.0 (mailto:search@abbiey.com)"},
            timeout=6.0,
        )
        resp.raise_for_status()
        for item in resp.json().get("message", {}).get("items", []):
            titles = item.get("title", [])
            title = titles[0] if titles else ""
            if not title:
                continue
            doi = item.get("DOI", "")
            url = f"https://doi.org/{doi}" if doi else ""
            if not url:
                continue
            abstract = re.sub(r"<[^>]+>", "", item.get("abstract", "")).strip()[:300]
            authors = item.get("author", [])
            author_str = ", ".join(
                f"{a.get('family', '')} {a.get('given', '')[:1]}".strip()
                for a in authors[:3]
            )
            pub = (item.get("container-title") or [""])[0]
            pd = item.get("published-print", item.get("published-online", {}))
            dp = (pd.get("date-parts") or [[]])[0] if pd else []
            year = str(dp[0]) if dp else ""
            body = abstract if abstract else " · ".join(filter(None, [author_str, pub, year]))
            results.append({
                "title": title,
                "url": url,
                "body": body,
                "source": "Crossref",
                "source_type": "academic",
            })
        if results:
            logger.info("Crossref: %d results", len(results))
    except Exception:
        logger.warning("Crossref search failed", exc_info=True)
    return results


def _try_internet_archive_text(query, max_results=15):
    """Search Internet Archive for texts/books/historical docs (no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": f"({query}) AND mediatype:texts",
                "output": "json",
                "rows": min(max_results, 50),
                "fl[]": ["identifier", "title", "description", "creator", "date"],
                "sort[]": "downloads desc",
            },
            timeout=5.0,
        )
        resp.raise_for_status()
        for doc in resp.json().get("response", {}).get("docs", []):
            identifier = doc.get("identifier", "")
            if not identifier:
                continue
            title = doc.get("title", identifier)
            if isinstance(title, list):
                title = title[0] if title else identifier
            desc = doc.get("description", "")
            if isinstance(desc, list):
                desc = desc[0] if desc else ""
            creator = doc.get("creator", "")
            if isinstance(creator, list):
                creator = creator[0] if creator else ""
            date = doc.get("date", "")
            body = desc[:300] if desc else ""
            if creator:
                body = f"{creator} — {body}" if body else creator
            if date:
                body = f"{body} ({date[:4]})" if body else date[:4]
            results.append({
                "title": title,
                "url": f"https://archive.org/details/{identifier}",
                "body": body.strip(),
                "source": "Internet Archive",
                "source_type": "archive",
            })
        if results:
            logger.info("Internet Archive texts: %d results", len(results))
    except Exception:
        logger.warning("Internet Archive texts failed", exc_info=True)
    return results


def _try_stract(query, max_results=20):
    """Search Stract — open-source, independent search engine (free API, no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://stract.com/api/search",
            params={"q": query, "num_results": min(max_results, 20)},
            headers={"Accept": "application/json"},
            timeout=6.0,
        )
        resp.raise_for_status()
        for r in resp.json().get("webpages", []):
            url = r.get("url", "")
            if not url:
                continue
            snippet = r.get("snippet", {})
            body = snippet.get("text", "") if isinstance(snippet, dict) else str(snippet or "")
            results.append({
                "title": r.get("title", ""),
                "url": url,
                "body": body,
                "source": "Stract",
                "source_type": "independent",
            })
        if results:
            logger.info("Stract: %d results", len(results))
    except Exception:
        logger.warning("Stract search failed", exc_info=True)
    return results


_SEARXNG_INSTANCES = [
    "https://search.mdosch.de",
    "https://searx.be",
    "https://searxng.site",
    "https://search.disroot.org",
]


def _try_searxng(query, max_results=20):
    """Query a public SearXNG instance — meta-search across many engines (no key required)."""
    for base in _SEARXNG_INSTANCES:
        results = []
        try:
            resp = _get_http().get(
                f"{base}/search",
                params={"q": query, "format": "json", "categories": "general"},
                headers={"User-Agent": "abbiey.search/1.0"},
                timeout=6.0,
            )
            if resp.status_code != 200:
                continue
            for r in resp.json().get("results", [])[:max_results]:
                url = r.get("url", "")
                if not url:
                    continue
                results.append({
                    "title": r.get("title", ""),
                    "url": url,
                    "body": r.get("content", ""),
                    "source": "SearXNG",
                    "source_type": "aggregator",
                })
            if results:
                logger.info("SearXNG (%s): %d results", base, len(results))
                return results
        except Exception:
            continue
    return []


def _try_reddit_text(query, max_results=15):
    """Search Reddit for top posts/discussions on any topic (no key required)."""
    import datetime as _dt
    results = []
    try:
        resp = _get_http().get(
            "https://www.reddit.com/search.json",
            params={"q": query, "sort": "relevance", "t": "all",
                    "limit": min(max_results, 25), "type": "link"},
            headers={"User-Agent": "abbiey.search/1.0 (privacy search engine)"},
            timeout=5.0,
        )
        resp.raise_for_status()
        for child in resp.json().get("data", {}).get("children", []):
            post = child.get("data", {})
            url = post.get("url", "")
            title = post.get("title", "")
            if not url or not title:
                continue
            score = post.get("score", 0)
            sub = post.get("subreddit_name_prefixed", "r/?")
            num_comments = post.get("num_comments", 0)
            selftext = (post.get("selftext") or "")[:200]
            body = (
                selftext
                if selftext and selftext not in ("[deleted]", "[removed]")
                else f"{sub} · {score:,} upvotes · {num_comments} comments"
            )
            results.append({
                "title": title,
                "url": url,
                "body": body,
                "source": f"Reddit · {sub}",
                "source_type": "community",
            })
        if results:
            logger.info("Reddit text: %d results", len(results))
    except Exception:
        logger.warning("Reddit text search failed", exc_info=True)
    return results


def _try_hackernews_text(query, max_results=10):
    """Search Hacker News stories and discussions (no key required)."""
    results = []
    try:
        resp = _get_http().get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "hitsPerPage": min(max_results, 20)},
            timeout=4.0,
        )
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            title = hit.get("title", "")
            if not title or not url:
                continue
            points = hit.get("points") or 0
            num_comments = hit.get("num_comments") or 0
            author = hit.get("author", "")
            created = (hit.get("created_at") or "")[:10]
            body = f"{points} points · {num_comments} comments · {author}"
            if created:
                body += f" · {created}"
            results.append({
                "title": title,
                "url": url,
                "body": body,
                "source": "Hacker News",
                "source_type": "community",
            })
        if results:
            logger.info("HackerNews text: %d results", len(results))
    except Exception:
        logger.warning("HackerNews text search failed", exc_info=True)
    return results


# ---- Price comparison helpers ----

def _extract_price(text):
    """Extract first price from text; returns (display_str, numeric_val)."""
    m = PRICE_RE.search(text or "")
    if not m:
        return None, None
    raw = m.group(0).strip()
    numeric_str = re.sub(r"[^\d.]", "", raw)
    try:
        return raw, float(numeric_str)
    except Exception:
        return raw, None


def _get_retailer(url):
    """Map a URL to a known retailer name."""
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        for d, name in RETAILER_DOMAINS.items():
            if d in domain:
                return name
        return domain.split(".")[0].capitalize()
    except Exception:
        return "Store"


def _try_prices(query, max_results=40):
    """Parallel DDG searches scoped to major retail sites; extracts prices from results."""
    site_queries = [
        f"{query} site:amazon.com OR site:amazon.com.au OR site:amazon.co.uk",
        f"{query} site:ebay.com OR site:ebay.com.au OR site:ebay.co.uk",
        f"{query} site:walmart.com OR site:bestbuy.com OR site:target.com OR site:newegg.com",
        f"{query} site:etsy.com OR site:costco.com OR site:bhphotovideo.com",
        f"{query} site:jbhifi.com.au OR site:harveynorman.com.au OR site:kogan.com OR site:officeworks.com.au",
        f"{query} buy price compare",
    ]

    seen_urls: set = set()
    results = []
    with ThreadPoolExecutor(max_workers=len(site_queries)) as pool:
        futs = [pool.submit(_try_ddg, q, 10, "text") for q in site_queries]
        for fut in as_completed(futs, timeout=10):
            try:
                for r in (fut.result() or []):
                    url = r.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    title = r.get("title", "")
                    body = r.get("body", "")
                    price_str, price_val = _extract_price(f"{title} {body}")
                    results.append({
                        "title": title,
                        "url": url,
                        "body": body,
                        "price": price_str,
                        "price_val": price_val,
                        "retailer": _get_retailer(url),
                        "source_type": "price",
                    })
            except Exception as exc:
                logger.warning("prices fetch error: %s", exc)

    with_price = sorted(
        [r for r in results if r.get("price_val") is not None],
        key=lambda x: x["price_val"],
    without_price = [r for r in results if r.get("price_val") is None]
    )
    return (with_price + without_price)[:max_results]


# ---- Alternatives helpers ----

def _try_alternativeto(query, max_results=16):
    """Scrape AlternativeTo search results page."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("beautifulsoup4 not installed — AlternativeTo fallback disabled")
        return []
    try:
        resp = _get_http().get(
            f"https://alternativeto.net/browse/search/?q={quote_plus(query)}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=8,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        seen = set()
        # Software links follow pattern /software/{name}/ or /software/{name}/about/
        sw_re = re.compile(r"^/software/([^/]+)/?(?:about/?)?$")
        for link in soup.find_all("a", href=sw_re):
            href = link.get("href", "").rstrip("/")
            slug = sw_re.match(href)
            if not slug:
                continue
            canonical = f"/software/{slug.group(1)}/"
            if canonical in seen:
                continue
            seen.add(canonical)
            name = link.get_text(strip=True) or slug.group(1).replace("-", " ").title()
            if len(name) < 2:
                continue
            # Search upward for a description paragraph
            description = ""
            card = link.find_parent(["article", "section", "li", "div"])
            if card:
                for p in card.find_all(["p", "span"]):
                    text = p.get_text(strip=True)
                    if 20 < len(text) < 300 and text.lower() != name.lower():
                        description = text
                        break
            # Platforms chips
            platforms = []
            if card:
                for chip in card.find_all(["li", "span"], class_=re.compile(r"platform|Platform", re.I)):
                    t = chip.get_text(strip=True)
                    if t and len(t) < 30:
                        platforms.append(t)
            results.append({
                "title": name,
                "url": f"https://alternativeto.net{canonical}",
                "body": description,
                "platforms": platforms[:5],
                "source": "AlternativeTo",
                "source_type": "alternative",
            })
            if len(results) >= max_results:
                break
        return results
    except Exception as exc:
        logger.warning("alternativeto scrape error: %s", exc)
        return []


def _try_alternatives_ddg(query, max_results=20):
    """DDG text search for alternatives on known comparison sites."""
    alt_query = (
        f'"{query}" alternatives '
        f'site:alternativeto.net OR site:slant.co OR site:g2.com OR site:capterra.com OR site:producthunt.com'
    )
    try:
        raw = _try_ddg(alt_query, max_results, "text") or []
        results = []
        for r in raw:
            url = r.get("url", "")
            domain = urlparse(url).netloc.lower().lstrip("www.")
            source_map = {
                "alternativeto.net": "AlternativeTo",
                "slant.co": "Slant",
                "g2.com": "G2",
                "capterra.com": "Capterra",
                "producthunt.com": "Product Hunt",
            }
            source = next((v for k, v in source_map.items() if k in domain), domain)
            results.append({
                "title": r.get("title", ""),
                "url": url,
                "body": r.get("body", ""),
                "platforms": [],
                "source": source,
                "source_type": "alternative",
            })
        return results
    except Exception as exc:
        logger.warning("alternatives DDG error: %s", exc)
        return []


# ---- Deduplication ----

def _deduplicate(results):
    """Remove duplicate results by URL, preserving order."""
    seen = set()
    unique = []
    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        unique.append(r)
    return unique


# ---- Onion / Deep Web backends ----

def _try_ahmia(query, max_results=30):
    """Scrape Ahmia.fi (clearnet Tor search engine) for .onion results.

    Ahmia requires a hidden anti-bot token from its homepage.
    We fetch the homepage first, extract the token, then search.
    """
    results = []
    try:
        client = _get_http()
        # Step 1: Fetch homepage to get anti-bot hidden field
        home_resp = client.get(
            "https://ahmia.fi/",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0"},
        )
        home_resp.raise_for_status()
        token_match = re.search(
            r'<input\s+type="hidden"\s+name="([^"]+)"\s+value="([^"]+)"',
            home_resp.text,
        )
        params = {"q": query}
        if token_match:
            params[token_match.group(1)] = token_match.group(2)

        # Step 2: Search with token (Ahmia returns large pages slowly, needs long timeout)
        resp = httpx.get(
            "https://ahmia.fi/search/",
            params=params,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:128.0) Gecko/20100101 Firefox/128.0"},
            timeout=20.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text

        # Ahmia result structure:
        #   <li class="result">
        #     <h4><a href="/search/redirect?...redirect_url=http://xxx.onion/...">Title</a></h4>
        #     <p>Snippet</p>
        #     <cite>xxx.onion</cite>
        #   </li>
        blocks = re.findall(
            r'<li\s+class="result">(.*?)</li>',
            html,
            re.DOTALL,
        )
        for block in blocks[:max_results]:
            link_match = re.search(
                r'<h4>\s*<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
            if not link_match:
                continue
            url = link_match.group(1).strip()
            title = re.sub(r"<[^>]+>", "", link_match.group(2)).strip()

            # Extract actual .onion URL from Ahmia's redirect wrapper
            if "redirect_url=" in url:
                qs = parse_qs(urlparse(url).query)
                if qs.get("redirect_url"):
                    url = qs["redirect_url"][0]

            # Snippet from <p>
            snippet_match = re.search(r'<p>(.*?)</p>', block, re.DOTALL)
            body = ""
            if snippet_match:
                body = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()

            if title and url:
                results.append({
                    "title": title,
                    "url": url,
                    "body": body,
                    "onion": True,
                })

        if results:
            logger.info("Ahmia: %d onion results", len(results))
    except Exception:
        logger.warning("Ahmia search failed", exc_info=True)
    return results


def _try_onion_ddg(query, max_results=30):
    """Search DDG for .onion-related results as a fallback.

    Regular search engines don't index .onion directly, so this returns
    clearnet pages that reference .onion sites for the given query.
    """
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(f"{query} .onion", max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "body": r.get("body", ""),
                    "onion": False,
                })
        if results:
            logger.info("DDG onion fallback: %d results", len(results))
    except Exception:
        logger.warning("DDG onion fallback failed", exc_info=True)
    return results


# ---- Orchestrator ----

def _fetch_results(
    query,
    page,
    search_type,
    region=None,
    lang=None,
    operators=None,
    time_filter=None,
    safesearch="off",
    image_opts=None,
    local_rank_context=None,
    anti_template=False,
    source_query_for_fallback=None,
):
    """Fetch results with caching. Returns paginated slice."""
    operators = operators or {}
    # Include operators in cache key to prevent cross-contamination
    ops_str = "&".join(f"{k}={','.join(v)}" for k, v in sorted(operators.items())) if operators else ""
    img_seg = ""
    if image_opts and search_type == "images":
        img_seg = "|img:" + json.dumps(image_opts, sort_keys=True, separators=(",", ":"))
    cw_seg = "|cw=1" if (search_type == "text" and anti_template) else ""
    cache_key = f"{query}|{search_type}|{region or ''}|{lang or ''}|{ops_str}|{time_filter or ''}|{safesearch or 'off'}{img_seg}{cw_seg}"

    # Check cache
    with _cache_lock:
        cached = _cache.get(cache_key)

    if cached is not None:
        # Serve from cache
        start = RESULTS_PER_PAGE * (page - 1)
        page_results = cached[start : start + RESULTS_PER_PAGE]
        has_more = len(cached) > start + RESULTS_PER_PAGE
        notice = None
        if search_type == "onion":
            if page_results and any(not r.get("onion", False) for r in page_results):
                notice = _ONION_FALLBACK_MSG
            elif not cached:
                notice = _ONION_UNAVAILABLE_MSG
        return {"results": page_results, "has_more": has_more, "page": page, "notice": notice}

    # In-flight deduplication: if another thread is already fetching the same key, wait for it
    _my_event = None
    with _in_flight_lock:
        if cache_key in _in_flight:
            _wait_event = _in_flight[cache_key]
        else:
            _my_event = threading.Event()
            _in_flight[cache_key] = _my_event
            _wait_event = None

    if _wait_event is not None:
        _wait_event.wait(timeout=10)
        with _cache_lock:
            cached = _cache.get(cache_key)
        if cached is not None:
            start = RESULTS_PER_PAGE * (page - 1)
            page_results = cached[start : start + RESULTS_PER_PAGE]
            has_more = len(cached) > start + RESULTS_PER_PAGE
            notice = None
            if search_type == "onion":
                if page_results and any(not r.get("onion", False) for r in page_results):
                    notice = _ONION_FALLBACK_MSG
                elif not cached:
                    notice = _ONION_UNAVAILABLE_MSG
            return {"results": page_results, "has_more": has_more, "page": page, "notice": notice}
        # Primary fetch failed or timed out — fall through and fetch ourselves.
        # Register our own event so subsequent waiters can piggyback on our result.
        _my_event = threading.Event()
        with _in_flight_lock:
            _in_flight[cache_key] = _my_event

    # Build effective query with operators
    effective_query = _build_engine_query(query, operators) if operators else query
    max_results = CACHE_FETCH_SIZE
    # Onion / Deep Web — dedicated path, skip normal engines
    results = []
    if search_type == "onion":
        try:
            results = _try_ahmia(effective_query)
        except Exception:
            logger.warning("_try_ahmia raised unexpectedly; falling through to DDG fallback", exc_info=True)
        if not results:
            logger.info("Ahmia empty, trying DDG onion fallback")
            try:
                results = _try_onion_ddg(effective_query)
            except Exception:
                logger.warning("_try_onion_ddg raised unexpectedly", exc_info=True)
    elif search_type == "code":
        # Code — dedicated path: fetch GitHub, StackOverflow, GitLab, npm in parallel.
        # Never use generic DDG — it returns unrelated web pages styled in code font.
        logger.info("Code search: fetching GitHub/SO/GitLab/npm in parallel")
        with ThreadPoolExecutor(max_workers=4) as _code_pool:
            _gh_fut  = _code_pool.submit(_try_github_search,   effective_query, max_results)
            _so_fut  = _code_pool.submit(_try_stackoverflow,   effective_query, max_results)
            _gl_fut  = _code_pool.submit(_try_gitlab,          effective_query, max_results)
            _npm_fut = _code_pool.submit(_try_npm,             effective_query, max_results)
            gh_res  = _gh_fut.result(timeout=8)  or []
            so_res  = _so_fut.result(timeout=8)  or []
            gl_res  = _gl_fut.result(timeout=8)  or []
            npm_res = _npm_fut.result(timeout=8) or []

        # Interleave sources so results aren't all from one platform
        seen_urls = set()
        for batch in zip_longest(gh_res, so_res, gl_res, npm_res):
            for r in batch:
                if r and r.get("url") not in seen_urls:
                    seen_urls.add(r.get("url"))
                    results.append(r)

        # Fallback: DDG with code-site filter if all APIs failed
        if not results:
            logger.info("Code APIs all failed, falling back to DDG code-focused")
            results = _try_code_ddg(effective_query, max_results)
    elif search_type == "prices":
        logger.info("Price search: fetching from retailers in parallel")
        results = _try_prices(effective_query, max_results)
    elif search_type == "alts":
        logger.info("Alternatives search: trying AlternativeTo + DDG fallback")
        results = _try_alternativeto(effective_query)
        if not results:
            logger.info("AlternativeTo empty, falling back to DDG alternatives search")
            results = _try_alternatives_ddg(effective_query, max_results)
    else:
        results = []
        skip_ddg = False
        if search_type == "images" and image_opts:
            results = _fetch_images_multi_source(
                effective_query, max_results, region, time_filter, safesearch, image_opts
            )
            skip_ddg = bool(results)

        pipeline_used = False
        if search_type == "text" and _retrieval_pipeline_enabled():
            try:
                _rp_fetchers = {
                    "ddg": lambda: _try_ddg(
                        effective_query, max_results, "text", region, time_filter, safesearch
                    ),
                    "wikipedia": lambda: _try_wikipedia(effective_query, lang),
                    "marginalia": lambda: _try_marginalia(query),
                    "stract": lambda: _try_stract(query),
                    "searxng": lambda: _try_searxng(query),
                    "hn": lambda: _try_hackernews_text(query),
                    "reddit": lambda: _try_reddit_text(query),
                    "archive": lambda: _try_internet_archive_text(query),
                }
                if _looks_academic(query):
                    _rp_fetchers["arxiv"] = lambda: _try_arxiv(query)
                    _rp_fetchers["pubmed"] = lambda: _try_pubmed(query)
                    _rp_fetchers["crossref"] = lambda: _try_crossref(query)
                _rp_hits = run_text_retrieval_pipeline_sync(
                    user_query=query,
                    effective_query=effective_query,
                    fetchers=_rp_fetchers,
                    max_results=max_results,
                    lang=lang,
                    region=region,
                    time_filter=time_filter,
                    safesearch=safesearch,
                )
                if _rp_hits:
                    results = _rp_hits
                    pipeline_used = True
                    skip_ddg = True
            except Exception:
                logger.exception("retrieval_pipeline_failed")

        if not skip_ddg:
            # Layer 1: DDG multi-backend (with timeout guard)
            try:
                with ThreadPoolExecutor(max_workers=1) as _ddg_pool:
                    _ddg_fut = _ddg_pool.submit(
                        _try_ddg, effective_query, max_results, search_type, region, time_filter, safesearch
                    )
                    results = _ddg_fut.result(timeout=5)
            except Exception:
                logger.exception("DDG failed/timed out for query=%s type=%s", query, search_type)

        # Text: parallel multi-source enrichment — blend deeper sources alongside DDG (legacy path)
        if search_type == "text" and not pipeline_used:
            existing_urls = {r.get("url", "") for r in results}
            _deep_pool = ThreadPoolExecutor(max_workers=10)
            try:
                _deep_futures = {
                    _deep_pool.submit(_try_marginalia, query): "marginalia",
                    _deep_pool.submit(_try_stract, query): "stract",
                    _deep_pool.submit(_try_searxng, query): "searxng",
                    _deep_pool.submit(_try_hackernews_text, query): "hn",
                    _deep_pool.submit(_try_reddit_text, query): "reddit",
                    _deep_pool.submit(_try_internet_archive_text, query): "archive",
                }
                if _looks_academic(query):
                    _deep_futures[_deep_pool.submit(_try_arxiv, query)] = "arxiv"
                    _deep_futures[_deep_pool.submit(_try_pubmed, query)] = "pubmed"
                    _deep_futures[_deep_pool.submit(_try_crossref, query)] = "crossref"
                deep_results = []
                done, pending = _futures_wait(_deep_futures.keys(), timeout=8)
                for _future in pending:
                    _future.cancel()
                for _future in done:
                    try:
                        for r in (_future.result() or []):
                            url = r.get("url", "")
                            if url and url not in existing_urls:
                                existing_urls.add(url)
                                deep_results.append(r)
                    except Exception:
                        pass
                # Surface academic results above community noise when query is academic
                if _looks_academic(query):
                    academic = [r for r in deep_results if r.get("source_type") == "academic"]
                    other = [r for r in deep_results if r.get("source_type") != "academic"]
                    results = results + academic + other
                else:
                    results = results + deep_results
            finally:
                _deep_pool.shutdown(wait=False)

        # Image-specific fallbacks — parallel
        if not results and search_type == "images":
            logger.info("Image search empty, trying parallel fallbacks")
            with ThreadPoolExecutor(max_workers=3) as _img_pool:
                _img_futs = [
                    _img_pool.submit(_try_openverse, query),
                    _img_pool.submit(_try_wikimedia_commons, query),
                    _img_pool.submit(_try_internet_archive_images, query, max_results),
                ]
                for fut in as_completed(_img_futs):
                    try:
                        r = fut.result(timeout=6)
                        if r:
                            results = r
                            break
                    except Exception:
                        pass

        # News-specific fallbacks — parallel
        if not results and search_type == "news":
            logger.info("News search empty, trying parallel fallbacks")
            with ThreadPoolExecutor(max_workers=4) as _news_pool:
                _news_futs = [
                    _news_pool.submit(_try_google_news_rss, query),
                    _news_pool.submit(_try_bing_news_rss, query),
                    _news_pool.submit(_try_hackernews, query, max_results),
                    _news_pool.submit(_try_reddit_news, query, max_results),
                ]
                for fut in as_completed(_news_futs):
                    try:
                        r = fut.result(timeout=6)
                        if r:
                            results = r
                            break
                    except Exception:
                        pass

        # Video-specific fallbacks — parallel
        if not results and search_type == "videos":
            logger.info("Video search empty, trying parallel fallbacks")
            with ThreadPoolExecutor(max_workers=2) as _vid_pool:
                _vid_futs = [
                    _vid_pool.submit(_try_internet_archive_videos, query, max_results),
                    _vid_pool.submit(_try_peertube, query, max_results),
                ]
                for fut in as_completed(_vid_futs):
                    try:
                        r = fut.result(timeout=6)
                        if r:
                            results = r
                            break
                    except Exception:
                        pass


    # Text-only deep fallbacks
    if not results and search_type == "text":
        logger.info("DDG empty, trying Marginalia")
        results = _try_marginalia(query)
    if not results and search_type == "text":
        logger.info("Marginalia empty, trying Wikipedia")
        results = _try_wikipedia(query, lang)
    if not results and search_type == "text":
        logger.info("Wikipedia empty, trying Wiby.me")
        results = _try_wiby(query)
    if not results and search_type == "text":
        logger.info("Wiby empty, trying Mojeek")
        results = _try_mojeek(query)
    if not results and search_type == "text":
        logger.info("All engines empty, trying DDG instant answers")
        results = _try_ddg_instant(query)
    if not results and search_type == "text":
        logger.info("Inclusive bridge: milder queries + curated portals (no blank SERP)")
        results = _inclusive_text_recovery_bridge(
            query,
            lang,
            region,
            time_filter,
            safesearch,
            raw_query=(source_query_for_fallback or "").strip() or None,
        )
    results = _deduplicate(results)
    if search_type == "text" and local_rank_context and local_rank_context.get("has_local_intent"):
        results = _rank_local_search_results(results, local_rank_context)
    elif search_type == "text" and anti_template:
        results = _rank_anti_template_results(results)
    # Store in cache and always release the in-flight lock so waiters are never stranded
    try:
        with _cache_lock:
            _cache[cache_key] = results
    finally:
        if _my_event is not None:
            with _in_flight_lock:
                _in_flight.pop(cache_key, None)
            _my_event.set()

    start = RESULTS_PER_PAGE * (page - 1)
    page_results = results[start : start + RESULTS_PER_PAGE]
    has_more = len(results) > start + RESULTS_PER_PAGE
    notice = None
    if search_type == "onion":
        if page_results and any(not r.get("onion", False) for r in page_results):
            notice = _ONION_FALLBACK_MSG
        elif not results:
            notice = _ONION_UNAVAILABLE_MSG

    return {"results": page_results, "has_more": has_more, "page": page, "notice": notice}


# ---------------------------------------------------------------------------
# Auth routes — signup / login / logout / profile
# ---------------------------------------------------------------------------
import re as _re

_USERNAME_RE = _re.compile(r'^[a-zA-Z0-9_]{3,30}$')

# Serialize signup attempts that reuse the same email+username pair (double-submit / parallel tabs).
_N_SIGNUP_LOCKS = 256
_SIGNUP_PARALLEL_LOCKS = tuple(threading.Lock() for _ in range(_N_SIGNUP_LOCKS))


def _signup_attempt_lock(email: str, username: str) -> threading.Lock:
    raw = f"{(email or '').strip().lower()}\x00{(username or '').strip().lower()}".encode(
        "utf-8", errors="ignore"
    )
    idx = int.from_bytes(hashlib.sha256(raw).digest()[:2], "big") % _N_SIGNUP_LOCKS
    return _SIGNUP_PARALLEL_LOCKS[idx]


def _signup_unique_conflict_field(exc: BaseException) -> str | None:
    """Classify DB unique violations so reused username/email get consistent messages (SQLite + PostgreSQL)."""
    msg_l = str(exc).lower()
    if isinstance(exc, sqlite3.IntegrityError) or "sqlite3" in type(exc).__module__:
        if "users.username" in msg_l or ("username" in msg_l and "unique" in msg_l):
            return "username"
        if "users.email" in msg_l or ("email" in msg_l and "unique" in msg_l):
            return "email"
        if "unique" in msg_l:
            return "unknown"
        return None
    pgcode = getattr(exc, "pgcode", None)
    if pgcode == "23505" or "duplicate key value violates unique constraint" in msg_l:
        diag = getattr(exc, "diag", None)
        cname = (getattr(diag, "constraint_name", None) or "").lower()
        detail = (getattr(diag, "message_detail", None) or "").lower()
        if "username" in cname or "username" in detail or "(username)=" in msg_l:
            return "username"
        if "email" in cname or "email" in detail or "(email)=" in msg_l:
            return "email"
        if "idx_users_username_lower" in msg_l:
            return "username"
        if "idx_users_email_lower" in msg_l:
            return "email"
        if "users_username" in msg_l or "username_key" in msg_l:
            return "username"
        if "users_email" in msg_l or "email_key" in msg_l:
            return "email"
        return "unknown"
    return None


def _require_login():
    """Return a redirect if not logged in, else None."""
    if not session.get("user_id"):
        return redirect(url_for("login", next=request.path))
    return None


def _safe_redirect_url(next_url: str) -> str:
    """Only allow relative redirects — prevents open-redirect attacks."""
    if not next_url:
        return url_for("index")
    parsed = urlparse(next_url)
    if parsed.netloc or parsed.scheme:
        return url_for("index")
    return next_url


def _sync_supabase_auth_user(email: str, display_name: str = "", phone: str | None = None) -> int | None:
    """Ensure a Supabase-authenticated user exists in our local users table. Returns user id."""
    email = (email or "").strip().lower()
    if not email:
        return None
    rows = _users_execute("SELECT id FROM users WHERE LOWER(email)=LOWER(?)", [email])
    if rows:
        uid = rows[0]["id"]
        if phone:
            try:
                _users_execute("UPDATE users SET phone=? WHERE id=?", [phone, uid])
            except Exception:
                logger.exception("sync_supabase_phone_update_failed")
        return uid
    username = email.split("@")[0][:30].lower()
    username = _re.sub(r'[^a-z0-9_]', '_', username)
    if len(username) < 3:
        username = username + "_user"
    # Deduplicate username
    base_username = username
    counter = 1
    while True:
        taken = _users_execute("SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)", [username])
        if not taken:
            break
        username = f"{base_username}{counter}"[:30]
        counter += 1
        if counter > 100:
            username = f"user_{secrets.token_hex(4)}"
            break
    try:
        rows = _users_execute(
            "INSERT INTO users (username, email, password_hash, display_name, email_verified) "
            "VALUES (?,?,?,?,?)",
            [username, email, "supabase_auth", display_name or username, True],
            return_id=True,
        )
        uid = _row_returning_id(rows)
        out = int(uid) if uid else None
        if out and phone:
            try:
                _users_execute("UPDATE users SET phone=? WHERE id=?", [phone, out])
            except Exception:
                logger.exception("sync_supabase_phone_insert_followup_failed")
        return out
    except Exception:
        # Race condition — another request created it
        rows = _users_execute("SELECT id FROM users WHERE LOWER(email)=LOWER(?)", [email])
        if not rows:
            return None
        rid = rows[0]["id"]
        if phone:
            try:
                _users_execute("UPDATE users SET phone=? WHERE id=?", [phone, rid])
            except Exception:
                logger.exception("sync_supabase_phone_race_update_failed")
        return rid


def _signup_process_post():
    """Create account from validated form. Raises on unexpected failure; returns Response or render str path."""
    username_raw = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    phone_raw = (request.form.get("phone") or "").strip()

    errors = []
    if not _USERNAME_RE.match(username_raw):
        errors.append("Username must be 3–30 characters: letters, numbers, underscores only.")
    if not email or "@" not in email:
        errors.append("A valid email address is required.")
    elif len(email) > 254:
        errors.append("Email address is too long.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if password != confirm:
        errors.append("Passwords do not match.")
    phone_norm = _normalize_e164_phone(phone_raw) if phone_raw else None
    if phone_raw and not phone_norm:
        errors.append("Invalid phone number. Use international format (e.g. +1 555 123 4567).")

    if errors:
        return render_template(
            "signup.html",
            errors=errors,
            username=username_raw,
            email=email,
            phone=phone_raw,
        )

    username_key = username_raw.lower()
    display_name = username_raw
    pw_hash = generate_password_hash(password)
    uid = None

    lock = _signup_attempt_lock(email, username_key)
    with lock:
        taken_u = _users_execute(
            "SELECT 1 AS taken FROM users WHERE LOWER(username)=LOWER(?) LIMIT 1",
            [username_key],
        )
        taken_e = _users_execute(
            "SELECT 1 AS taken FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1",
            [email],
        )
        if taken_u:
            errors.append(
                "That username is already taken. Sign in if it is yours, or choose another username."
            )
        if taken_e:
            errors.append(
                "An account with that email already exists. Sign in or use a different email address."
            )
        if errors:
            return render_template(
                "signup.html",
                errors=errors,
                username=username_raw,
                email=email,
                phone=phone_raw,
            )

        try:
            rows = _users_execute(
                "INSERT INTO users (username, email, password_hash, display_name, email_verified, phone) "
                "VALUES (?,?,?,?,?,?)",
                [username_key, email, pw_hash, display_name, False, phone_norm],
                return_id=True,
            )
            uid = _row_returning_id(rows)
        except Exception as exc:
            field = _signup_unique_conflict_field(exc)
            if field == "username":
                errors.append(
                    "That username is already taken. Sign in if it is yours, or choose another username."
                )
            elif field == "email":
                errors.append(
                    "An account with that email already exists. Sign in or use a different email address."
                )
            else:
                logger.warning("signup_insert_failed: %s", exc)
                errors.append("Account could not be created. Please try again.")
            return render_template(
                "signup.html",
                errors=errors,
                username=username_raw,
                email=email,
                phone=phone_raw,
            )

    if not uid:
        logger.error(
            "signup_missing_user_id after insert email=%s username=%s", email, username_key
        )
        return render_template(
            "signup.html",
            errors=["Account could not be created. Please try again."],
            username=username_raw,
            email=email,
            phone=phone_raw,
        )
    try:
        otp, vtok = _set_verification_challenge(int(uid))
    except Exception:
        logger.exception("verification_challenge_failed uid=%s", uid)
        return render_template(
            "signup.html",
            errors=["Account was created but verification could not be started. Please contact support."],
            username=username_raw,
            email=email,
            phone=phone_raw,
        )
    sent = _send_signup_verification_email(email, display_name, otp, vtok)
    vq = {"email": email, "new": "1"}
    if not sent:
        vq["email_failed"] = "1"
    return redirect(url_for("verify_email", **vq))


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("100/hour")
def signup():
    uid = session.get("user_id")
    if uid:
        u = _get_user_by_id(uid)
        if u and _user_is_email_verified(u):
            return redirect(url_for("profile"))
        session.pop("user_id", None)

    sb_ctx = {"supabase_url": _SUPABASE_URL, "supabase_anon_key": _SUPABASE_ANON_KEY, "supabase_auth": _SUPABASE_AUTH_ENABLED}

    if request.method == "GET":
        return render_template("signup.html", **sb_ctx)

    try:
        return _signup_process_post()
    except Exception:
        logger.exception("signup_post_unhandled")
        return render_template(
            "signup.html",
            errors=[
                "Something went wrong while creating your account. Please try again. "
                "If you already registered, sign in instead."
            ],
            username=(request.form.get("username") or "").strip(),
            email=(request.form.get("email") or "").strip().lower(),
            phone=(request.form.get("phone") or "").strip(),
            **sb_ctx,
        )
@app.route("/verify-email", methods=["GET", "POST"])
@limiter.limit("120/hour")
def verify_email():
    token = (request.args.get("token") or "").strip()
    if request.method == "GET" and token:
        rows = _users_execute("SELECT * FROM users WHERE verify_token=? LIMIT 1", [token])
        if not rows:
            return render_template(
                "verify_email.html",
                errors=["That link is invalid or has already been used."],
            )
        u = rows[0]
        if _user_is_email_verified(u):
            return render_template(
                "verify_email.html",
                errors=["That account is already verified. You can sign in."],
                verified_hint=True,
            )
        if not _ts_still_valid(u.get("verify_token_expires")):
            em = (u.get("email") or "").strip().lower()
            return render_template(
                "verify_email.html",
                errors=["That link has expired. Enter your email below and request a new code."],
                email=em,
            )
        try:
            uid_ok = int(u["id"])
        except (TypeError, ValueError):
            return render_template("verify_email.html", errors=["Something went wrong. Try again."])
        _mark_email_verified(uid_ok)
        session.permanent = True
        session["user_id"] = uid_ok
        flash("welcome", "welcome")
        r = redirect(url_for("search") + "?welcome=1")
        _set_welcome_seen_cookie(r)
        return r

    if request.method == "POST":
        email_in = (request.form.get("email") or "").strip().lower()
        code = (request.form.get("code") or "").strip().replace(" ", "")
        errors = []
        if not email_in or "@" not in email_in:
            errors.append("Enter the email you used to sign up.")
        if not code or not code.isdigit() or len(code) != 6:
            errors.append("Enter the 6-digit code from your email.")
        if errors:
            return render_template("verify_email.html", errors=errors, email=email_in)
        rows = _users_execute("SELECT * FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1", [email_in])
        if not rows:
            return render_template(
                "verify_email.html",
                errors=["No account found for that email. Check the address or sign up again."],
                email=email_in,
            )
        u = rows[0]
        if _user_is_email_verified(u):
            return render_template(
                "verify_email.html",
                errors=["That email is already verified. You can sign in."],
                email=email_in,
                verified_hint=True,
            )
        if not _ts_still_valid(u.get("otp_expires")):
            return render_template(
                "verify_email.html",
                errors=["That code has expired. Request a new code below."],
                email=email_in,
            )
        try:
            uid_ok = int(u["id"])
        except (TypeError, ValueError):
            return render_template("verify_email.html", errors=["Something went wrong. Try again."], email=email_in)
        expect = (u.get("otp_code_hash") or "").strip()
        if not expect or not hmac.compare_digest(expect, _otp_digest(uid_ok, code)):
            return render_template(
                "verify_email.html",
                errors=["That code is not correct."],
                email=email_in,
            )
        _mark_email_verified(uid_ok)
        session.permanent = True
        session["user_id"] = uid_ok
        flash("welcome", "welcome")
        r = redirect(url_for("search") + "?welcome=1")
        _set_welcome_seen_cookie(r)
        return r

    email_q = (request.args.get("email") or "").strip().lower()
    return render_template(
        "verify_email.html",
        email=email_q,
        from_signup=(request.args.get("new") == "1"),
        resent=(request.args.get("resent") == "1"),
        email_failed=(request.args.get("email_failed") == "1"),
    )
@app.route("/verify-email/resend", methods=["POST"])
@limiter.limit("8/hour")
def verify_email_resend():
    email_in = (request.form.get("email") or "").strip().lower()
    if not email_in or "@" not in email_in:
        return render_template(
            "verify_email.html",
            errors=["Enter your email address."],
            email=email_in,
        )
    rows = _users_execute("SELECT * FROM users WHERE LOWER(email)=LOWER(?) LIMIT 1", [email_in])
    if not rows or _user_is_email_verified(rows[0]):
        return redirect(url_for("verify_email", email=email_in, resent="1"))
    u = rows[0]
    try:
        uid_ok = int(u["id"])
    except (TypeError, ValueError):
        return redirect(url_for("verify_email", email=email_in, resent="1"))
    try:
        otp, vtok = _set_verification_challenge(uid_ok)
    except Exception:
        logger.exception("verify_resend_challenge_failed")
        return render_template(
            "verify_email.html",
            errors=["Could not send a new code right now. Try again in a few minutes."],
            email=email_in,
        )
    disp = u.get("display_name") or u.get("username") or "there"
    sent = _send_signup_verification_email(email_in, disp, otp, vtok)
    rq = {"email": email_in, "resent": "1"}
    if not sent:
        rq["email_failed"] = "1"
    return redirect(url_for("verify_email", **rq))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("120/hour")
def login():
    uid = session.get("user_id")
    if uid:
        u = _get_user_by_id(uid)
        if u and _user_is_email_verified(u):
            return redirect(url_for("profile"))
        session.pop("user_id", None)

    sb_ctx = {"supabase_url": _SUPABASE_URL, "supabase_anon_key": _SUPABASE_ANON_KEY, "supabase_auth": _SUPABASE_AUTH_ENABLED}

    if request.method == "GET":
        return render_template("login.html", next=request.args.get("next", ""), **sb_ctx)

    identifier = request.form.get("identifier", "").strip()
    password   = request.form.get("password", "")
    next_url   = request.form.get("next", "")

    try:
        user = _get_user_by_login(identifier)
    except Exception:
        logger.exception("login_lookup_failed")
        return render_template(
            "login.html",
            error="Something went wrong. Please try again in a moment.",
            identifier=identifier,
            next=next_url,
            **sb_ctx,
        )
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html",
            error="Invalid email/username or password.",
            identifier=identifier,
            next=next_url,
            **sb_ctx,
        )
    if not _user_is_email_verified(user):
        return render_template(
            "login.html",
            error=(
                "Please verify your email before signing in. Check your inbox for a 6-digit code and link, "
                "or use the verification page to request a new email."
            ),
            identifier=identifier,
            next=next_url,
            verify_email_hint=True,
            **sb_ctx,
        )
    session.permanent = True
    try:
        session["user_id"] = int(user["id"])
    except (TypeError, ValueError):
        session["user_id"] = user["id"]
    return redirect(_safe_redirect_url(next_url))


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.pop("user_id", None)
    resp = redirect(url_for("index"))
    resp.delete_cookie(_SB_ACCESS_TOKEN_COOKIE, path="/")
    return resp


@app.route("/auth/callback", methods=["POST"])
@limiter.limit("60/minute")
def auth_callback():
    """Client-side Supabase Auth sends us the session after sign-in/sign-up.
    We sync the user into our DB and set a Flask session."""
    if not _SUPABASE_AUTH_ENABLED:
        return jsonify({"error": "Supabase Auth not configured"}), 400
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    display_name = (data.get("display_name") or "").strip()
    phone_raw = (data.get("phone") or "").strip()
    access_token = (data.get("access_token") or "").strip()
    phone_e164 = None
    if phone_raw:
        phone_e164 = _normalize_e164_phone(phone_raw)
        if not phone_e164:
            return jsonify({"error": "Invalid phone number. Use international format (e.g. +1 555 123 4567)."}), 400
    if not email or "@" not in email:
        return jsonify({"error": "Invalid email"}), 400
    try:
        uid = _sync_supabase_auth_user(email, display_name, phone_e164)
    except Exception:
        logger.exception("auth_callback_sync_failed")
        return jsonify({"error": "Could not sync account"}), 500
    if not uid:
        return jsonify({"error": "Could not create account"}), 500
    session.permanent = True
    session["user_id"] = uid
    resp = jsonify({"ok": True, "user_id": uid})
    _set_welcome_seen_cookie(resp)
    if access_token:
        _set_sb_access_token_cookie(resp, access_token)
    return resp


@app.route("/auth/confirm")
def auth_confirm():
    """Landing page after Supabase OAuth redirect (e.g. Google). JS picks up the session."""
    if not _SUPABASE_AUTH_ENABLED:
        return redirect(url_for("login"))
    return render_template("auth_confirm.html")


@app.route("/forgot-password")
def forgot_password():
    """Password reset page — uses Supabase Auth resetPasswordForEmail."""
    return render_template("forgot_password.html")


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _user_id_from_api_key(token: str) -> int | None:
    """Resolve a raw secret key to user id, or None if unknown/revoked."""
    if not token or not token.startswith(ABBIEY_API_KEY_PREFIX):
        return None
    if len(token) < len(ABBIEY_API_KEY_PREFIX) + 8:
        return None
    digest = _hash_api_key(token)
    try:
        rows = _users_execute(
            "SELECT user_id FROM api_keys WHERE key_hash=? AND revoked_at IS NULL LIMIT 1",
            [digest],
        )
    except Exception:
        logger.exception("api_key_lookup_failed")
        return None
    if not rows:
        return None
    try:
        return int(rows[0]["user_id"])
    except (TypeError, ValueError, KeyError):
        return None


def _api_auth_user():
    """
    Resolve the account for this request: valid Bearer API key, or session.

    Returns (user_id, error_response) where error_response is a Flask (response, status)
    tuple only when Authorization: Bearer was sent but invalid (must return 401).
    If no Bearer, error_response is None and user_id may be None (caller decides 401 vs soft fail).
    """
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if not token:
            return None, (jsonify({"error": "Invalid API key"}), 401)
        uid = _user_id_from_api_key(token)
        if uid is None:
            return None, (jsonify({"error": "Invalid or revoked API key"}), 401)
        return uid, None
    return session.get("user_id"), None


def _list_api_keys_for_user(uid: int) -> list:
    return _users_execute(
        "SELECT id, label, key_last_four, created_at FROM api_keys "
        "WHERE user_id=? AND revoked_at IS NULL ORDER BY created_at DESC",
        [uid],
    )
def _count_active_api_keys(uid: int) -> int:
    rows = _users_execute(
        "SELECT COUNT(*) AS n FROM api_keys WHERE user_id=? AND revoked_at IS NULL",
        [uid],
    )
    if not rows:
        return 0
    return int(rows[0].get("n") or 0)


@app.route("/developer")
def developer():
    uid = session.get("user_id")
    keys = []
    if uid:
        try:
            keys = _list_api_keys_for_user(uid)
        except Exception:
            logger.exception("developer_keys_list_failed")
            session["api_key_error"] = "Could not load API keys. Please refresh the page."
    reveal = session.pop("api_key_reveal_once", None)
    err = session.pop("api_key_error", None)
    billing_success = request.args.get("billing", "").strip().lower() == "success"
    return render_template(
        "developer.html",
        api_keys=keys,
        reveal_key=reveal,
        api_key_error=err,
        billing_success=billing_success,
        stripe_api_checkout_url=STRIPE_API_KEYS_CHECKOUT_URL,
    )
@app.route("/developer/api-keys/create", methods=["POST"])
@limiter.limit("30/hour")
def developer_api_key_create():
    if not session.get("user_id"):
        return redirect(url_for("login", next=url_for("developer")))
    uid = session["user_id"]
    try:
        key_count = _count_active_api_keys(uid)
    except Exception:
        logger.exception("api_key_count_failed")
        session["api_key_error"] = "Could not verify your keys. Please try again."
        return redirect(url_for("developer"))
    if key_count >= _MAX_API_KEYS_PER_USER:
        session["api_key_error"] = (
            f"You can have at most {_MAX_API_KEYS_PER_USER} active keys. "
            "Revoke one to create another."
        )
        return redirect(url_for("developer"))
    label = (request.form.get("label") or "").strip()[:60]
    raw_suffix = secrets.token_urlsafe(28)
    full_key = ABBIEY_API_KEY_PREFIX + raw_suffix
    key_last_four = full_key[-4:]
    key_hash = _hash_api_key(full_key)
    try:
        _users_execute(
            "INSERT INTO api_keys (user_id, label, key_last_four, key_hash) VALUES (?,?,?,?)",
            [uid, label, key_last_four, key_hash],
        )
    except Exception as exc:
        logging.warning("api_keys insert failed: %s", exc)
        session["api_key_error"] = "Could not create a key. Please try again."
        return redirect(url_for("developer"))
    session["api_key_reveal_once"] = full_key
    return redirect(url_for("developer"))


@app.route("/developer/api-keys/<int:key_id>/revoke", methods=["POST"])
@limiter.limit("60/hour")
def developer_api_key_revoke(key_id):
    if not session.get("user_id"):
        return redirect(url_for("login", next=url_for("developer")))
    uid = session["user_id"]
    try:
        _users_execute(
            "UPDATE api_keys SET revoked_at=datetime('now') WHERE id=? AND user_id=? AND revoked_at IS NULL",
            [key_id, uid],
        )
    except Exception:
        logger.exception("api_key_revoke_failed")
        session["api_key_error"] = "Could not revoke that key. Please try again."
    return redirect(url_for("developer"))


# ---------------------------------------------------------------------------
# Digital animal (gamified avatar) — XP, leaderboard, tiers
# ---------------------------------------------------------------------------
def _pet_day_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _pet_ensure_row(uid: int) -> None:
    _users_execute(
        "INSERT OR IGNORE INTO user_pet (user_id) VALUES (?)",
        [uid],
    )


def _pet_try_award(uid: int, action: str) -> dict:
    """Award XP when daily / rate limits allow."""
    if action not in _digital_pet.PET_ACTION_XP:
        return {"ok": False, "xp_awarded": 0, "reason": "unknown_action"}
    base = _digital_pet.PET_ACTION_XP[action]
    try:
        _pet_ensure_row(uid)
    except Exception:
        logger.exception("pet_ensure_failed")
        return {"ok": False, "xp_awarded": 0, "reason": "db"}

    if action == "share":
        recent = _users_execute(
            "SELECT id FROM pet_activity_log WHERE user_id=? AND action='share' "
            "AND created_at > datetime('now', '-2 minutes') LIMIT 1",
            [uid],
        )
        if recent:
            return {"ok": False, "xp_awarded": 0, "reason": "share_cooldown"}

    if action == "search":
        cnt_rows = _users_execute(
            "SELECT COUNT(*) AS c FROM pet_activity_log WHERE user_id=? AND action='search' "
            "AND created_at > datetime('now', '-1 hour')",
            [uid],
        )
        n = int(cnt_rows[0].get("c", 0) or 0) if cnt_rows else 0
        if n >= _digital_pet.SEARCH_MAX_PER_HOUR:
            return {"ok": False, "xp_awarded": 0, "reason": "search_hourly_cap"}

    day = _pet_day_utc()
    daily_rows = _users_execute(
        "SELECT xp FROM pet_daily_xp WHERE user_id=? AND day_utc=?",
        [uid, day],
    )
    daily_so_far = int(daily_rows[0]["xp"]) if daily_rows else 0
    room = max(0, _digital_pet.DAILY_XP_CAP - daily_so_far)
    if room <= 0:
        return {"ok": False, "xp_awarded": 0, "reason": "daily_cap", "daily_remaining": 0}
    grant = min(base, room)

    try:
        _users_execute(
            "INSERT INTO pet_activity_log (user_id, action, xp) VALUES (?,?,?)",
            [uid, action, grant],
        )
        _users_execute(
            "UPDATE user_pet SET xp_total = xp_total + ?, last_activity_at = datetime('now') WHERE user_id=?",
            [grant, uid],
        )
        dr = _users_execute("SELECT xp FROM pet_daily_xp WHERE user_id=? AND day_utc=?", [uid, day])
        if dr:
            _users_execute(
                "UPDATE pet_daily_xp SET xp = xp + ? WHERE user_id=? AND day_utc=?",
                [grant, uid, day],
            )
        else:
            _users_execute(
                "INSERT INTO pet_daily_xp (user_id, day_utc, xp) VALUES (?,?,?)",
                [uid, day, grant],
            )
    except Exception:
        logger.exception("pet_award_failed uid=%s action=%s", uid, action)
        return {"ok": False, "xp_awarded": 0, "reason": "db"}

    return {"ok": True, "xp_awarded": grant, "daily_remaining": room - grant}


def _pet_rank_and_tier(uid: int, xp_total: int) -> tuple[int, float, str]:
    """Rank among users with XP > 0; percentile 0 = best. Returns (rank, pct, tier)."""
    if xp_total <= 0:
        return (0, 1.0, "novice")
    tot_rows = _users_execute("SELECT COUNT(*) AS c FROM user_pet WHERE xp_total > 0", [])
    total = int(tot_rows[0]["c"]) if tot_rows else 0
    if total <= 0:
        return (1, 0.0, "platinum")
    better = _users_execute(
        "SELECT COUNT(*) AS c FROM user_pet WHERE xp_total > ? OR (xp_total = ? AND user_id < ?)",
        [xp_total, xp_total, uid],
    )
    n_better = int(better[0]["c"]) if better else 0
    rank = n_better + 1
    pct = (rank - 1) / max(total - 1, 1) if total > 1 else 0.0
    return (rank, pct, _digital_pet.tier_from_percentile_rank(pct))


def _pet_bookmark_cap_for_uid(uid: int) -> int:
    rows = _users_execute("SELECT xp_total FROM user_pet WHERE user_id=?", [uid])
    if not rows:
        return _digital_pet.bookmark_cap_for_tier("novice")
    xp = int(rows[0].get("xp_total") or 0)
    _r, _p, tier = _pet_rank_and_tier(uid, xp)
    return _digital_pet.bookmark_cap_for_tier(tier)


_PET_SPECIES_LABELS = {
    "hummingbird": "Hummingbird",
    "firefly": "Firefly",
    "snake": "Snake",
    "dolphin": "Dolphin",
}


def _pet_snapshot_for_user(uid: int) -> dict:
    rows = _users_execute(
        "SELECT species, xp_total FROM user_pet WHERE user_id=?",
        [uid],
    )
    if not rows:
        return {
            "has_pet": False,
            "species": "hummingbird",
            "species_label": _PET_SPECIES_LABELS["hummingbird"],
            "xp_total": 0,
            "level": 1,
            "stage": 0,
            "tier": "novice",
            "rank": 0,
        }
    species = (rows[0].get("species") or "hummingbird").lower()
    if species not in _digital_pet.PET_SPECIES:
        species = "hummingbird"
    xp = int(rows[0].get("xp_total") or 0)
    rank, _pct, tier = _pet_rank_and_tier(uid, xp)
    return {
        "has_pet": True,
        "species": species,
        "species_label": _PET_SPECIES_LABELS.get(species, species.title()),
        "xp_total": xp,
        "level": _digital_pet.level_from_xp(xp),
        "stage": _digital_pet.stage_from_xp(xp),
        "tier": tier,
        "rank": rank,
    }


@app.route("/pet")
def pet_home():
    redir = _require_login()
    if redir:
        return redir
    uid = _session_user_id_int(session.get("user_id"))
    if not uid:
        return redirect(url_for("login", next="/pet"))
    snap = _pet_snapshot_for_user(uid)
    return render_template("pet.html", pet=snap, species_list=list(_digital_pet.PET_SPECIES))


@app.route("/pet/leaderboard")
def pet_leaderboard():
    rows = []
    try:
        rows = _users_execute(
            "SELECT u.username, u.display_name, p.species, p.xp_total, p.last_activity_at, u.id AS user_id, u.created_at "
            "FROM user_pet p INNER JOIN users u ON u.id = p.user_id "
            "WHERE p.xp_total > 0 "
            "ORDER BY p.xp_total DESC, p.last_activity_at DESC, u.created_at ASC "
            "LIMIT 100",
            [],
        )
    except Exception:
        logger.exception("pet_leaderboard_failed")
    ranked = []
    for i, r in enumerate(rows or [], start=1):
        xp = int(r.get("xp_total") or 0)
        uid = int(r["user_id"])
        st = _digital_pet.stage_from_xp(xp)
        ranked.append(
            {
                "rank": i,
                "username": r.get("username") or "",
                "display_name": r.get("display_name") or "",
                "species": (r.get("species") or "hummingbird").lower(),
                "xp_total": xp,
                "level": _digital_pet.level_from_xp(xp),
                "stage": st,
                "is_you": uid == _session_user_id_int(session.get("user_id")),
            }
        )
    return render_template("pet_leaderboard.html", leaderboard=ranked)


@app.route("/api/pet/me", methods=["GET"])
def api_pet_me():
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"pet": _pet_snapshot_for_user(uid)})


@app.route("/api/pet/species", methods=["POST"])
@limiter.limit("30/minute")
def api_pet_species():
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json(silent=True) or {}
    sp = (data.get("species") or "").strip().lower()
    if sp not in _digital_pet.PET_SPECIES:
        return jsonify({"error": "Invalid species"}), 400
    try:
        _pet_ensure_row(uid)
        _users_execute("UPDATE user_pet SET species=? WHERE user_id=?", [sp, uid])
    except Exception:
        logger.exception("api_pet_species_failed")
        return jsonify({"error": "Could not save"}), 503
    return jsonify({"ok": True, "pet": _pet_snapshot_for_user(uid)})


@app.route("/api/pet/activity", methods=["POST"])
@limiter.limit("120/minute")
def api_pet_activity():
    """Client-reported actions (e.g. share). Server enforces cooldowns and caps."""
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip().lower()
    if action != "share":
        return jsonify({"error": "Unsupported action"}), 400
    out = _pet_try_award(uid, "share")
    out["pet"] = _pet_snapshot_for_user(uid)
    return jsonify(out)


@app.route("/profile")
def profile():
    redir = _require_login()
    if redir:
        return redir

    uid = session["user_id"]
    try:
        user = _get_user_by_id(uid)
        if not user:
            session.pop("user_id", None)
            return redirect(url_for("login"))

        bcap = _pet_bookmark_cap_for_uid(uid)
        bookmarks = _users_execute(
            "SELECT * FROM user_bookmarks WHERE user_id=? ORDER BY saved_at DESC LIMIT ?",
            [uid, int(bcap)],
        )
        history = _users_execute(
            "SELECT query, search_type, searched_at FROM user_search_history"
            " WHERE user_id=? ORDER BY searched_at DESC LIMIT 50",
            [uid],
        )
    except Exception:
        logger.exception("profile_load_failed")
        return (
            render_template(
                "error.html",
                code=503,
                title="Could not load profile",
                message="We couldn't load your account right now. Please try again in a moment.",
                extra_help=True,
            ),
            503,
        )
    return render_template("profile.html", user=user, bookmarks=bookmarks, history=history)


@app.route("/profile/update", methods=["POST"])
def profile_update():
    redir = _require_login()
    if redir:
        return redir

    uid          = session["user_id"]
    display_name = request.form.get("display_name", "").strip()[:60]
    bio          = request.form.get("bio", "").strip()[:200]
    phone_raw = (request.form.get("phone") or "").strip()
    phone_e164 = _normalize_e164_phone(phone_raw) if phone_raw else None
    if phone_raw and not phone_e164:
        flash("Invalid phone number. Use international format (e.g. +1 555 123 4567).", "error")
        return redirect(url_for("profile"))

    try:
        _users_execute(
            "UPDATE users SET display_name=?, bio=?, phone=? WHERE id=?",
            [display_name or None, bio, phone_e164 if phone_raw else None, uid],
        )
    except Exception:
        logger.exception("profile_update_failed")
        return (
            render_template(
                "error.html",
                code=503,
                title="Could not save profile",
                message="Your changes could not be saved. Please try again shortly.",
                extra_help=False,
            ),
            503,
        )
    return redirect(url_for("profile"))


# ---- Avatar upload ----------------------------------------------------------

@app.route("/profile/avatar", methods=["POST"])
def profile_avatar():
    redir = _require_login()
    if redir:
        return redir

    uid = session["user_id"]
    f = request.files.get("avatar")
    if not f or not f.content_type or not f.content_type.startswith("image/"):
        return redirect(url_for("profile"))

    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
    ext = ext_map.get(f.content_type, "jpg")

    if os.environ.get("VERCEL"):
        # On Vercel filesystem is read-only — skip saving
        return redirect(url_for("profile"))

    save_dir = os.path.join(os.path.dirname(__file__), "static", "avatars")
    os.makedirs(save_dir, exist_ok=True)
    filename = f"{uid}.{ext}"
    f.save(os.path.join(save_dir, filename))

    avatar_path = f"avatars/{filename}"
    try:
        _users_execute("UPDATE users SET avatar=? WHERE id=?", [avatar_path, uid])
    except Exception:
        logger.exception("profile_avatar_db_failed")

    return redirect(url_for("profile"))


# ---- Bookmarks API (session or Bearer API key) ------------------------------

@app.route("/api/user/me", methods=["GET"])
def api_user_me():
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        user = _get_user_by_id(uid)
    except Exception:
        logger.exception("api_user_me_lookup_failed")
        return jsonify({"error": "Could not load account. Try again later."}), 503
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify(
        {
            "id": user["id"],
            "username": user["username"],
            "display_name": user.get("display_name"),
        }
    )


@app.route("/api/user/bookmarks", methods=["GET"])
def api_user_bookmarks_get():
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        rows = _users_execute(
            "SELECT id, url, title, snippet, saved_at FROM user_bookmarks"
            " WHERE user_id=? ORDER BY saved_at DESC",
            [uid],
        )
    except Exception:
        logger.exception("api_user_bookmarks_get_failed")
        return jsonify({"error": "Could not load bookmarks.", "bookmarks": []}), 503
    return jsonify({"bookmarks": rows})


@app.route("/api/user/recent-searches", methods=["GET"])
def api_user_recent_searches():
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify([]), 401
    try:
        rows = _users_execute(
            "SELECT query, search_type FROM user_search_history"
            " WHERE user_id=? ORDER BY searched_at DESC LIMIT 5",
            [uid],
        )
    except Exception:
        logger.exception("api_user_recent_searches_failed")
        return jsonify([]), 503
    seen = set()
    unique = []
    for r in rows:
        if r["query"] not in seen:
            seen.add(r["query"])
            unique.append({"query": r["query"], "type": r["search_type"] or "text"})
    return jsonify(unique)


@app.route("/api/user/bookmarks", methods=["POST"])
@limiter.limit("1000/day")
def api_user_bookmarks_save():
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json(silent=True) or {}
    url     = (data.get("url") or "").strip()[:2000]
    title   = (data.get("title") or "").strip()[:300]
    snippet = (data.get("snippet") or "").strip()[:500]
    if not url:
        return jsonify({"error": "URL is required"}), 400
    try:
        rows = _users_execute(
            "INSERT OR IGNORE INTO user_bookmarks (user_id, url, title, snippet)"
            " VALUES (?,?,?,?)",
            [uid, url, title, snippet],
            return_id=True,
        )
        bid = rows[0]["id"] if rows else None
    except Exception:
        logger.exception("api_user_bookmarks_post_failed")
        return jsonify({"error": "Could not save bookmark. Try again later."}), 503
    if bid:
        try:
            _pet_try_award(uid, "bookmark")
        except Exception:
            pass
    return jsonify({"ok": True, "id": bid}), 201


@app.route("/api/user/bookmarks", methods=["DELETE"])
def api_user_bookmarks_delete_by_url():
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    url = (request.args.get("url") or "").strip()[:2000]
    if not url:
        data = request.get_json(silent=True) or {}
        url = str(data.get("url") or "").strip()[:2000]
    if not url:
        return jsonify({"error": "URL is required"}), 400
    try:
        _users_execute(
            "DELETE FROM user_bookmarks WHERE url=? AND user_id=?",
            [url, uid],
        )
    except Exception:
        return jsonify({"error": "Could not remove bookmark."}), 503
    return jsonify({"ok": True})


@app.route("/api/user/bookmarks/<int:bid>", methods=["DELETE"])
def api_user_bookmarks_delete(bid: int):
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        _users_execute(
            "DELETE FROM user_bookmarks WHERE id=? AND user_id=?", [bid, uid]
        )
    except Exception:
        logger.exception("api_user_bookmarks_delete_failed")
        return jsonify({"error": "Could not remove bookmark."}), 503
    return jsonify({"ok": True})


@app.route("/api/user/bookmarks/sync", methods=["POST"])
@limiter.limit("100/hour")
def api_user_bookmarks_sync():
    """Accept a list of localStorage bookmarks and upsert them server-side."""
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    items = (request.get_json(silent=True) or {}).get("bookmarks", [])
    saved = 0
    failed = 0
    for item in items[:500]:
        url     = str(item.get("url") or "")[:2000].strip()
        title   = str(item.get("title") or "")[:300].strip()
        snippet = str(item.get("snippet") or "")[:500].strip()
        if not url:
            continue
        try:
            _users_execute(
                "INSERT OR IGNORE INTO user_bookmarks (user_id, url, title, snippet)"
                " VALUES (?,?,?,?)",
                [uid, url, title, snippet],
            )
            saved += 1
        except Exception:
            failed += 1
            logger.warning("bookmark_sync_item_failed uid=%s url=%s", uid, url[:200], exc_info=True)
    try:
        rows = _users_execute(
            "SELECT id, url, title, snippet, saved_at FROM user_bookmarks"
            " WHERE user_id=? ORDER BY saved_at DESC",
            [uid],
        )
    except Exception:
        logger.exception("api_user_bookmarks_sync_readback_failed")
        return jsonify({"ok": False, "saved": saved, "failed": failed, "bookmarks": []}), 503
    return jsonify({"ok": failed == 0, "saved": saved, "failed": failed, "bookmarks": rows})


@app.route("/api/user/history", methods=["POST"])
def api_user_history_add():
    """Record a search query for the logged-in user."""
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"ok": False}), 200  # silent when anonymous (no Bearer)
    data = request.get_json(silent=True) or {}
    q    = (data.get("query") or "").strip()[:500]
    st   = (data.get("search_type") or "text")[:20]
    if not q:
        return jsonify({"ok": False}), 200
    try:
        _users_execute(
            "INSERT INTO user_search_history (user_id, query, search_type)"
            " VALUES (?,?,?)",
            [uid, q, st],
        )
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/user/history", methods=["GET"])
@limiter.limit("120/minute")
def api_user_history_get():
    """Return deduplicated search history for the logged-in user (up to 50)."""
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"history": []}), 401
    try:
        rows = _users_execute(
            "SELECT query, search_type, searched_at FROM user_search_history"
            " WHERE user_id=? ORDER BY searched_at DESC LIMIT 200",
            [uid],
        )
    except Exception:
        logger.exception("api_user_history_get_failed")
        return jsonify({"history": []}), 503
    seen: set = set()
    unique = []
    for r in rows:
        if r["query"] not in seen:
            seen.add(r["query"])
            unique.append({
                "query": r["query"],
                "type": r["search_type"] or "text",
                "at": r["searched_at"],
            })
        if len(unique) >= 50:
            break
    return jsonify({"history": unique})


@app.route("/api/user/history", methods=["DELETE"])
@limiter.limit("120/minute")
def api_user_history_delete():
    """Delete one query or clear all history for the logged-in user."""
    uid, bearer_err = _api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"ok": False}), 401
    data = request.get_json(silent=True) or {}
    if data.get("clear_all"):
        try:
            _users_execute(
                "DELETE FROM user_search_history WHERE user_id=?",
                [uid],
            )
        except Exception:
            logger.exception("api_user_history_clear_failed")
            return jsonify({"ok": False}), 503
        return jsonify({"ok": True, "cleared": True})
    q = (data.get("query") or "").strip()[:500]
    if not q:
        return jsonify({"ok": False, "error": "query required"}), 400
    try:
        _users_execute(
            "DELETE FROM user_search_history WHERE user_id=? AND query=?",
            [uid, q],
        )
    except Exception:
        logger.exception("api_user_history_delete_failed")
        return jsonify({"ok": False}), 503
    return jsonify({"ok": True})


@app.route("/opensearch.xml")
def opensearch():
    base = _site_base_url()
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
  <ShortName>abbieysearch</ShortName>
  <Description>Private, fast, no-tracking search engine</Description>
  <Tags>privacy search private</Tags>
  <Contact>hello@abbieysearch.com</Contact>
  <Url type="text/html" template="{base}/search?q={{searchTerms}}"/>
  <Url type="application/opensearchdescription+xml" rel="self"
       template="{base}/opensearch.xml"/>
  <Image height="16" width="16" type="image/x-icon">{base}/static/favicon.ico</Image>
  <InputEncoding>UTF-8</InputEncoding>
  <OutputEncoding>UTF-8</OutputEncoding>
</OpenSearchDescription>'''
    return Response(xml, mimetype="application/opensearchdescription+xml")


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "abbieysearch",
        "short_name": "abbieysearch",
        "description": "Privacy-first web search — no account required",
        "start_url": "/search",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#000000",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
        ],
        "categories": ["search", "productivity", "utilities"],
        "shortcuts": [
            {"name": "Web Search", "url": "/search?type=text", "description": "Search the web privately"},
            {"name": "Image Search", "url": "/search?type=images", "description": "Search images privately"},
            {"name": "News Search", "url": "/search?type=news", "description": "Search news privately"}
        ]
    })


@app.route("/robots.txt")
def robots():
    base = _site_base_url()
    txt = f"""User-agent: *
Allow: /
Allow: /search
Disallow: /api/
Disallow: /profile
Disallow: /profile/update
Disallow: /logout

Sitemap: {base}/sitemap.xml
"""
    return Response(txt, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    base = _site_base_url()
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{base}/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{base}/search</loc>
    <changefreq>daily</changefreq>
    <priority>0.95</priority>
  </url>
  <url>
    <loc>{base}/login</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>{base}/signup</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>{base}/breach-check</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>
  <url>
    <loc>{base}/privacy</loc>
    <changefreq>monthly</changefreq>
    <priority>0.85</priority>
  </url>
  <url>
    <loc>{base}/terms</loc>
    <changefreq>monthly</changefreq>
    <priority>0.85</priority>
  </url>
  <url>
    <loc>{base}/about</loc>
    <changefreq>weekly</changefreq>
    <priority>0.9</priority>
  </url>
</urlset>'''
    return Response(xml, mimetype="application/xml")


@app.route("/favicon.ico")
def favicon_ico():
    return redirect("/static/icon-192.png", code=301)


# ── Breach Check ──────────────────────────────────────────────────────────────

@app.route("/breach-check")
def breach_check():
    return render_template("breach_check.html", deploy_hash=_get_deploy_hash())


@app.route("/api/breach-check", methods=["POST"])
@limiter.limit("40 per minute")
def api_breach_check():
    """Check an email address against the XposedOrNot breach database."""
    body = request.get_json(silent=True) or {}
    email = body.get("email", "").strip().lower()

    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Please enter a valid email address."}), 400

    try:
        resp = _get_http().get(
            f"https://api.xposedornot.com/v1/breach-analytics?email={quote_plus(email)}",
            timeout=12,
            headers={"User-Agent": "abbiey.search/1.0 (breach-check)"},
            follow_redirects=True,
        )
        if resp.status_code == 404:
            return jsonify({"breaches": [], "total": 0, "email": _mask_email(email)})
        if resp.status_code == 429:
            return jsonify({"error": "Rate limit reached. Please try again in a moment."}), 429
        if resp.status_code != 200:
            return jsonify({"error": "Breach database unavailable. Try again shortly."}), 502

        data = resp.json()

        # XposedOrNot returns {"Error":"Not found"} when email has no breaches
        if "Error" in data:
            return jsonify({"breaches": [], "total": 0, "email": _mask_email(email)})

        raw = (data.get("ExposedBreaches") or {}).get("breaches_details") or []
        breaches = []
        for b in raw:
            exposed_data = b.get("xposed_data") or []
            if isinstance(exposed_data, str):
                exposed_data = [x.strip() for x in exposed_data.split(",") if x.strip()]
            breaches.append({
                "name": b.get("breach") or "Unknown",
                "date": b.get("xposed_date") or "",
                "count": b.get("xposed_records") or 0,
                "data": exposed_data,
                "industry": b.get("industry") or "",
                "logo": b.get("logo_path") or "",
                "password_risk": b.get("password_risk") or "",
            })

        return jsonify({
            "breaches": breaches,
            "total": len(breaches),
            "email": _mask_email(email),
        })

    except Exception as exc:
        logging.warning("breach_check error: %s", exc)
        return jsonify({"error": "Could not complete the breach check. Please try again."}), 500


def _mask_email(email: str) -> str:
    """Return a partially masked email for display (e.g. jo***@example.com)."""
    try:
        local, domain = email.split("@", 1)
        visible = local[:2] if len(local) > 2 else local[:1]
        return f"{visible}***@{domain}"
    except Exception:
        return "***"


@app.route("/api/password-check")
@limiter.limit("100 per minute")
def api_password_check():
    """Proxy the HIBP k-anonymity range API. Receives only a 5-char SHA-1 prefix."""
    prefix = request.args.get("prefix", "").upper()
    if not prefix or len(prefix) != 5 or not re.match(r"^[0-9A-F]{5}$", prefix):
        return jsonify({"error": "Invalid hash prefix"}), 400

    try:
        resp = _get_http().get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            timeout=10,
            headers={
                "Add-Padding": "true",
                "User-Agent": "abbiey.search/1.0 (password-check)",
            },
        )
        if resp.status_code != 200:
            return jsonify({"error": "HIBP service unavailable"}), 502
        return Response(resp.text, content_type="text/plain")
    except Exception as exc:
        logging.warning("password_check error: %s", exc)
        return jsonify({"error": "Could not check password"}), 500


@app.after_request
def _set_cache_headers(response):
    """Set appropriate cache headers based on response type and path."""
    try:
        path = request.path or ""
        # Static assets — long-lived immutable cache
        if path.startswith("/static/") and any(
            path.endswith(ext)
            for ext in (".css", ".js", ".woff2", ".woff", ".ttf", ".png", ".ico", ".svg", ".webp")
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
        # Trends / autocomplete API — short public cache
        if path in ("/api/trends", "/api/autocomplete", "/api/suggestions"):
            response.headers["Cache-Control"] = "public, max-age=60, s-maxage=60"
            return response
        # Search page and HTML — never cache
        ct = (response.content_type or "") if response.content_type else ""
        if path == "/search" or ("text/html" in ct):
            response.headers["Cache-Control"] = "no-store"
            return response
        return response
    except Exception:
        logger.exception("_set_cache_headers_failed")
        return response


if __name__ == "__main__":
    import os

    env = os.environ.get("ENV", "dev").lower()
    port = int(os.environ.get("PORT", 8000))

    is_dev = env in ("dev", "development", "local")

    app.run(
        host="127.0.0.1" if is_dev else "0.0.0.0",
        port=port,
        debug=is_dev,
        use_reloader=is_dev,
        threaded=True
    )
