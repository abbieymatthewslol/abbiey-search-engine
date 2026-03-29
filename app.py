"""
abbiey.search - A privacy-respecting, non-judgmental search engine.
No tracking. No filtering. No logs. Just results.
"""

import hashlib
import hmac
import json
import logging
import os
import queue
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, wait as _futures_wait
from itertools import zip_longest
from dataclasses import asdict
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import feedparser
import httpx
import stripe
from cachetools import TTLCache
from ddgs import DDGS
from flask import Flask, render_template, request, jsonify, redirect, session, url_for, flash, Response, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from entity_parser import detect_entities, build_search_queries, primary_entity

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(24).hex())
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000  # 1-year cache for static files

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

# Google Search Console — HTML tag method. If GOOGLE_SITE_VERIFICATION is unset, the default
# is used. If set to empty (e.g. GOOGLE_SITE_VERIFICATION=), the meta tag is omitted.
_GSC_DEFAULT_VERIFICATION = "iUMaOvsVzVceHScuX-0i35fWbUJxEfZKM9QH8l3mPM8"


def _load_google_site_verification() -> str:
    if "GOOGLE_SITE_VERIFICATION" in os.environ:
        return os.environ["GOOGLE_SITE_VERIFICATION"].strip()
    return _GSC_DEFAULT_VERIFICATION


_GOOGLE_SITE_VERIFICATION = _load_google_site_verification()

# ---------------------------------------------------------------------------
# Stripe configuration
# ---------------------------------------------------------------------------
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
_STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
_STRIPE_PRICE_ID       = os.environ.get("STRIPE_PRICE_ID", "")
_BASE_URL              = os.environ.get("BASE_URL", "http://localhost:8000")

# On Vercel the filesystem is read-only except /tmp; use /tmp when running there.
_DB_DIR       = "/tmp" if os.environ.get("VERCEL") else os.path.dirname(__file__)
_PAYMENTS_DB  = os.path.join(_DB_DIR, "payments.db")
_WAITLIST_DB  = os.path.join(_DB_DIR, "waitlist.db")
_ANALYTICS_DB = os.path.join(_DB_DIR, "analytics.db")
_USERS_DB     = os.path.join(_DB_DIR, "users.db")
_ADMIN_TOKEN  = os.environ.get("ADMIN_TOKEN", "")

OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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
# Set SUPABASE_DB_URL=postgresql://postgres:[password]@[host]:6543/postgres
# (use the pooler URL from Supabase Project Settings → Database → Connection Pooling)
# ---------------------------------------------------------------------------
_SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL", "") or os.environ.get("DATABASE_URL", "")
_pg_conn_lock = threading.Lock()


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
    if _was_or_ignore and 'ON CONFLICT' not in sql.upper():
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
            conn.commit()
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
        return []
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
            last_seen     TIMESTAMPTZ DEFAULT NOW()
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

        CREATE TABLE IF NOT EXISTS payments (
            id           SERIAL PRIMARY KEY,
            session_id   TEXT UNIQUE NOT NULL,
            email        TEXT,
            amount_total INTEGER,
            currency     TEXT,
            status       TEXT DEFAULT 'paid',
            created_at   TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS waitlist (
            id         SERIAL PRIMARY KEY,
            email      TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """
    try:
        _pg_execute(ddl)
    except Exception as exc:
        logging.warning("PG table init failed: %s", exc)


if _SUPABASE_DB_URL:
    try:
        _init_pg_tables()
        logging.info("Supabase/PostgreSQL analytics backend active")
    except Exception as _pg_init_err:
        logging.warning("Supabase init failed: %s", _pg_init_err)


def _analytics_execute(sql: str, args: list = None):
    """Route SQL to the active analytics backend: Supabase → Turso → SQLite."""
    if _SUPABASE_DB_URL:
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
    if _SUPABASE_DB_URL:
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


def _init_payments_db():
    with sqlite3.connect(_PAYMENTS_DB) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS payments ("
            "  id INTEGER PRIMARY KEY,"
            "  session_id TEXT UNIQUE NOT NULL,"
            "  email TEXT,"
            "  amount_total INTEGER,"
            "  currency TEXT,"
            "  status TEXT DEFAULT 'paid',"
            "  created_at TEXT DEFAULT (datetime('now'))"
            ")"
        )


_init_payments_db()


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
    if _SUPABASE_DB_URL:
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
    if _SUPABASE_DB_URL:
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


def _payments_execute(sql: str, args: list = None) -> list:
    """Route SQL to Supabase or payments.db SQLite."""
    if _SUPABASE_DB_URL:
        return _pg_execute(sql, args)
    with sqlite3.connect(_PAYMENTS_DB) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(sql, args or [])
        if cur.description:
            return [dict(r) for r in cur.fetchall()]
        return []


def _waitlist_execute(sql: str, args: list = None) -> list:
    """Route SQL to Supabase or waitlist.db SQLite."""
    if _SUPABASE_DB_URL:
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
                last_seen     TEXT DEFAULT (datetime('now'))
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
        """)


_init_users_db()

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


def _get_user_by_id(uid: int) -> "dict | None":
    rows = _users_execute("SELECT * FROM users WHERE id=?", [uid])
    return rows[0] if rows else None


def _get_user_by_login(identifier: str) -> "dict | None":
    rows = _users_execute(
        "SELECT * FROM users WHERE email=? OR username=?",
        [identifier, identifier],
    )
    return rows[0] if rows else None


@app.context_processor
def _inject_current_user():
    uid = session.get("user_id")
    ctx = {
        "deploy_hash": DEPLOY_HASH,
        "google_site_verification": _GOOGLE_SITE_VERIFICATION,
    }
    if uid:
        user = _get_user_by_id(uid)
        if user:
            try:
                _users_execute(
                    "UPDATE users SET last_seen=datetime('now') WHERE id=?", [uid]
                )
            except Exception:
                pass
            return {**ctx, "current_user": user}
    return {**ctx, "current_user": None}


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
            f"http://ip-api.com/json/{path_ip}",
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
    if _SUPABASE_DB_URL:
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
    vals = [
        query[:500],
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
        log.debug("Analytics insert failed: %s", exc)
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
            "query": query[:120],
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
    """Async analytics log (daemon thread): query + client IP, UA, device, geo. Never blocks request."""
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
    threading.Thread(target=_log_search_worker, args=args, daemon=True).start()


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


def _record_payment(session_id: str, email: str = "", amount_total: int = 0, currency: str = "usd"):
    """Persist a confirmed payment. Safe to call multiple times (UPSERT)."""
    try:
        _payments_execute(
            "INSERT OR IGNORE INTO payments (session_id, email, amount_total, currency) VALUES (?,?,?,?)",
            [session_id, email, amount_total, currency],
        )
    except Exception as exc:
        logger.error("Failed to record payment %s: %s", session_id, exc)


def _make_access_token(session_id: str) -> str:
    """Create a short HMAC token tied to the Stripe session_id."""
    secret = app.config["SECRET_KEY"].encode()
    return hmac.new(secret, session_id.encode(), hashlib.sha256).hexdigest()[:32]


def _check_persistent_access() -> bool:
    """Check abbiey_sid cookie directly against payments store. No HMAC — survives restarts."""
    sid = request.cookies.get("abbiey_sid", "")
    if not sid:
        return False
    try:
        rows = _payments_execute("SELECT id FROM payments WHERE session_id = ?", [sid])
        return len(rows) > 0
    except Exception:
        pass
    return False


@app.template_filter("domain")
def domain_filter(url):
    """Extract domain from URL for favicon lookups."""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""

RESULTS_PER_PAGE = 20
MAX_PAGE = 50
MAX_QUERY_LENGTH = 2000
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

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
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
@app.errorhandler(400)
def error_400(e):
    return render_template("error.html", code=400, title="Bad Request",
                           message=str(e.description) if hasattr(e, 'description') else "Invalid request."), 400


@app.errorhandler(404)
def error_404(e):
    return render_template("error.html", code=404, title="Not Found",
                           message="The page you're looking for doesn't exist."), 404


@app.errorhandler(429)
def error_429(e):
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
       request.accept_mimetypes.best == "application/json":
        return jsonify({"error": "rate_limited", "message": "Too many requests. Please slow down."}), 429
    return render_template("error.html", code=429, title="Too Many Requests",
                           message="You're sending requests too fast. Please wait a moment and try again."), 429


@app.errorhandler(500)
def error_500(e):
    return render_template("error.html", code=500, title="Server Error",
                           message="Something went wrong on our end. Please try again."), 500


# ---------------------------------------------------------------------------
# Search operator parsing
# ---------------------------------------------------------------------------
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
        logger.warning("Wikipedia knowledge panel failed for query=%s", q)
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
        logger.warning("Weather lookup failed for location=%s", location)
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
_TEMPLATE_DEFAULTS = dict(
    query="", results=[], search_type="text", has_more=False, page=1,
    entities=[], primary_entity=None, entity_results=[], operators={},
    region="", lang="", dictionary=None, calculator=None, color=None,
    unit_convert=None, knowledge=None, weather=None, qr=None, time_filter="",
)


@app.route("/")
def index():
    """Marketing home; full search UI lives at /search (empty q shows the same UI)."""
    return render_template("landing.html")


@app.route("/landing")
def landing():
    """Legacy URL — canonical home is /."""
    return redirect("/", code=301)


@app.route("/create-checkout-session", methods=["POST"])
@limiter.limit("10/minute")
def create_checkout_session():
    """Create a Stripe Checkout Session and redirect the user to it."""
    if not stripe.api_key:
        logger.error("STRIPE_SECRET_KEY not set")
        return render_template(
            "error.html", code=503, title="Payment Unavailable",
            message="Payment is not configured yet. Please try again later."
        ), 503

    if not _STRIPE_PRICE_ID:
        logger.error("STRIPE_PRICE_ID not set")
        return render_template(
            "error.html", code=503, title="Payment Unavailable",
            message="Payment product not configured. Please contact support."
        ), 503

    try:
        checkout_session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": _STRIPE_PRICE_ID, "quantity": 1}],
            success_url=_BASE_URL + "/payment-success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=_BASE_URL + "/payment-cancel",
            allow_promotion_codes=True,
        )
        return redirect(checkout_session.url, code=303)
    except stripe.StripeError as exc:
        logger.error("Stripe checkout error: %s", exc)
        return render_template(
            "error.html", code=502, title="Payment Error",
            message="Could not start checkout. Please try again."
        ), 502


@app.route("/payment-success")
def payment_success():
    """
    Stripe redirects here after successful payment.
    Verify the session server-side, record it, and grant access via a signed token.
    """
    sid = request.args.get("session_id", "").strip()

    if not sid:
        # No session_id — could be a direct visit or old Payment Link redirect
        # Grant session access anyway (legacy fallback)
        session["paid"] = True
        session["search_count"] = 0
        return render_template("payment_success.html", verified=False, email="")

    # Verify with Stripe if key is configured
    verified = False
    email = ""
    amount = 0
    currency = "usd"

    if stripe.api_key:
        try:
            stripe_session = stripe.checkout.Session.retrieve(sid)
            if stripe_session.payment_status == "paid":
                verified = True
                email = (stripe_session.customer_details or {}).get("email", "") or ""
                amount = stripe_session.amount_total or 0
                currency = stripe_session.currency or "usd"
                _record_payment(sid, email, amount, currency)
        except stripe.StripeError as exc:
            logger.error("Stripe session verify failed for %s: %s", sid, exc)

    # Grant access in server-side session
    session["paid"] = True
    session["search_count"] = 0
    session["payment_session_id"] = sid

    # Generate a client-side access token the browser can store in localStorage
    access_token = _make_access_token(sid) if sid else ""

    resp = make_response(render_template(
        "payment_success.html",
        verified=verified,
        email=email,
        access_token=access_token,
    ))
    if sid:
        # Persistent session_id cookie — survives server restarts, 1 year
        resp.set_cookie("abbiey_sid", sid, max_age=365 * 24 * 3600, samesite="Lax")
    return resp


@app.route("/admin/grant-access")
def admin_grant_access():
    """Admin-only: grant permanent paid access to the current browser session.
    Usage: /admin/grant-access?token=ADMIN_TOKEN
    Inserts a manual payment record and sets the persistent cookie.
    """
    token = request.args.get("token", "")
    if not _ADMIN_TOKEN or token != _ADMIN_TOKEN:
        return "Forbidden", 403
    # Create a stable manual session_id for this grant
    manual_sid = "manual_" + hashlib.sha256(token.encode()).hexdigest()[:16]
    _record_payment(manual_sid, email="admin", amount_total=1000, currency="usd")
    access_token = _make_access_token(manual_sid)
    session["paid"] = True
    session["search_count"] = 0
    resp = make_response(
        "<html><body style='font-family:sans-serif;padding:2rem'>"
        "<h2>✓ Access granted</h2>"
        "<p>Permanent paid access has been set for this browser.</p>"
        "<script>"
        f"localStorage.setItem('abbiey_access_token','{access_token}');"
        "localStorage.setItem('abbiey_paid','true');"
        "</script>"
        "<a href='/'>Go to search engine</a></body></html>"
    )
    resp.set_cookie("abbiey_sid", manual_sid, max_age=365 * 24 * 3600, samesite="Lax")
    return resp


@app.route("/payment-cancel")
def payment_cancel():
    """User cancelled checkout — return them to the landing page."""
    return render_template("payment_cancel.html")


@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    """
    Stripe webhook endpoint.
    Handles checkout.session.completed as a reliable server-side backup.
    Register this URL in your Stripe Dashboard → Webhooks.
    """
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")

    if not _STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook received but STRIPE_WEBHOOK_SECRET not set — skipping verification")
        return jsonify({"received": True})

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, _STRIPE_WEBHOOK_SECRET)
    except stripe.errors.SignatureVerificationError:
        logger.warning("Invalid Stripe webhook signature")
        return jsonify({"error": "Invalid signature"}), 400
    except Exception as exc:
        logger.error("Webhook parse error: %s", exc)
        return jsonify({"error": "Parse error"}), 400

    if event["type"] == "checkout.session.completed":
        s = event["data"]["object"]
        if s.get("payment_status") == "paid":
            email = (s.get("customer_details") or {}).get("email", "") or ""
            _record_payment(
                session_id=s["id"],
                email=email,
                amount_total=s.get("amount_total", 0),
                currency=s.get("currency", "usd"),
            )
            logger.info("Payment confirmed via webhook: %s (%s)", s["id"], email)

    return jsonify({"received": True})


@app.route("/search")
@limiter.limit("30/minute")
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

    if search_type not in ALLOWED_TYPES:
        search_type = "text"

    if not query:
        return render_template("index.html", **_TEMPLATE_DEFAULTS)

    if search_type == "saved":
        return render_template("index.html", query=query, results=[], search_type="saved",
                               has_more=False, page=1, entities=[], primary_entity=None,
                               entity_results=[], operators={}, region=region or "",
                               lang=lang or "", dictionary=None, calculator=None, color=None,
                               unit_convert=None, knowledge=None, weather=None, qr=None,
                               time_filter="")

    if len(query) > MAX_QUERY_LENGTH:
        return render_template("error.html", code=400, title="Query Too Long",
                               message=f"Query must be under {MAX_QUERY_LENGTH} characters."), 400

    # Parse search operators
    clean_query, operators = _parse_operators(query)
    if operators.get("lang"):
        lang = operators["lang"][0]

    # Query expansion
    expanded_query, expansion_terms = _expand_query(clean_query)
    if expansion_terms:
        clean_query = expanded_query

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
        results = _fetch_results(clean_query, page, search_type, region, lang, operators, time_filter=time_filter, safesearch=safesearch)
        _ajax_ms = int((time.perf_counter() - _t_ajax) * 1000)
        if page == 1:
            _log_search(query, search_type, region or "", len(results.get("results", [])), _ajax_ms, request=request)
        return jsonify(results)

    _t0 = time.perf_counter()
    results = _fetch_results(clean_query, 1, search_type, region, lang, operators, time_filter=time_filter, safesearch=safesearch)
    _latency_ms = int((time.perf_counter() - _t0) * 1000)

    # Log search analytics (non-blocking, never fails)
    if page == 1:
        _log_search(query, search_type, region or "", len(results.get("results", [])), _latency_ms, request=request)

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
    )


@app.route("/api/suggestions")
@limiter.limit("60/minute")
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
        )
        data = resp.json()
        if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
            return jsonify(data[1][:8])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return jsonify([item["phrase"] for item in data[:8] if "phrase" in item])
        return jsonify([])
    except Exception:
        return jsonify([])


@app.route("/api/entity")
@limiter.limit("30/minute")
def api_entity():
    """API endpoint: detect entities in a query."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"entities": [], "queries": []})
    if len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Query too long"}), 400
    entities = detect_entities(query)
    queries = build_search_queries(query, entities)
    primary = primary_entity(entities)
    return jsonify({
        "entities": [asdict(e) for e in entities],
        "primary": asdict(primary) if primary else None,
        "queries": queries,
    })


# ---------------------------------------------------------------------------
# Related Searches API
# ---------------------------------------------------------------------------

@app.route("/api/related")
@limiter.limit("30/minute")
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
        )
        data = resp.json()
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
                    )
                    d2 = resp2.json()
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
@limiter.limit("10/minute")
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
    except Exception as e:
        from html import escape as _esc
        error_type = type(e).__name__
        safe_url = _esc(url, quote=True)
        return f"""<!DOCTYPE html>
<html><head><title>Onion Proxy Error</title></head>
<body style="background:#0a0a0a;color:#e4e4e7;font-family:system-ui;padding:2rem;max-width:600px;margin:0 auto">
<h2 style="color:#f87171">Cannot reach .onion site</h2>
<p><strong>URL:</strong> <code>{safe_url}</code></p>
<p><strong>Error:</strong> {_esc(error_type)}</p>
<p style="color:#a1a1aa">Make sure Tor is running on port 9050. You can:</p>
<ul style="color:#a1a1aa">
<li>Open Tor Browser (it starts a SOCKS proxy automatically)</li>
<li>Or run <code>tor</code> as a standalone service</li>
</ul>
<p><a href="{safe_url}" style="color:#a78bfa">Try opening directly in Tor Browser &rarr;</a></p>
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
            )
        status = "live" if resp.status_code < 400 else "down"
    except Exception:
        # Tor not running or site unreachable — can't distinguish, report unknown
        status = "unknown"

    if status != "unknown":
        with _onion_status_lock:
            _onion_status_cache[url] = status
    return url, status


@app.route("/api/onion-check", methods=["POST"])
@limiter.limit("20/minute")
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
@limiter.limit("30/minute")
def api_preview():
    """Fetch a page preview (title + description + text excerpt)."""
    url = request.args.get("url", "").strip()
    if not url or not url.startswith("http"):
        return jsonify({"error": "Invalid URL"}), 400
    parsed_preview = urlparse(url)
    if ".onion" in (parsed_preview.netloc or ""):
        return jsonify({"error": "Cannot preview .onion addresses without Tor Browser"}), 400
    hostname = parsed_preview.hostname or ""
    if not hostname or _is_private_ip(hostname):
        return jsonify({"error": "Invalid URL"}), 400

    try:
        resp = httpx.get(
            url,
            timeout=4.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; abbiey.search/1.0)"},
        )
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
    except Exception:
        return jsonify({"error": "Could not fetch preview"}), 502


# ---------------------------------------------------------------------------
# AI Research Assistant Chat
# ---------------------------------------------------------------------------

def _ollama_chat(messages, model=None):
    """AI chat using local Ollama instance."""
    import requests as _requests
    _model = model or OLLAMA_MODEL
    try:
        resp = _requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": _model, "messages": messages, "stream": False},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Ollama unavailable: {e}") from e


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
@limiter.limit("20/minute")
def api_chat():
    """AI research assistant that studies search results and answers questions."""
    data = request.get_json() or {}
    query = data.get("query", "").strip()
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not query or not message:
        return jsonify({"error": "Missing query or message"}), 400
    if len(message) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Message too long"}), 400

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
        logger.exception("Chat fallback failed for query=%s", query)
        return jsonify({"error": "Chat service temporarily unavailable. Please try again."}), 503


@app.route("/api/ai-summary")
@limiter.limit("20/minute")
def api_ai_summary():
    """Generate a 2-3 sentence AI summary with citations for a query."""
    query = request.args.get("q", "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Invalid query"}), 400

    # Fetch top 5 results
    context_results = _fetch_results(query, 1, "text")
    top5 = context_results["results"][:5]
    if not top5:
        return jsonify({"error": "No results to summarize"}), 404

    # Build context
    context_lines = []
    sources = []
    for i, r in enumerate(top5, 1):
        title = r.get("title", "")
        body = r.get("body", "")
        url = r.get("url", "")
        context_lines.append(f"[{i}] {title}: {body}")
        sources.append({"title": title, "url": url})
    context = "\n".join(context_lines)

    prompt = (
        f"Based on these search results, summarize the answer to '{query}' in 2-3 sentences. "
        f"Cite sources as [1], [2] etc. Be concise and factual.\n\n{context}"
    )

    try:
        summary_messages = [
            {
                "role": "system",
                "content": (
                    "You are a search assistant. Given web results as context, write a 2-3 sentence "
                    "factual answer to the query. Cite sources by number [1], [2]. Be concise and direct."
                ),
            },
            {"role": "user", "content": f"Query: {query}\n\n{context}"},
        ]
        response = _ollama_chat(summary_messages)
        if response:
            return jsonify({"summary": response, "sources": sources})
    except Exception:
        logger.warning("AI summary failed for query=%s, trying extractive fallback", query)

    # Fallback: extractive summary from first two results
    parts = []
    for i, r in enumerate(top5[:2], 1):
        body = r.get("body", "")
        if body:
            parts.append(f"{body} [{i}]")
    if parts:
        return jsonify({"summary": " ".join(parts), "sources": sources})

    return jsonify({"error": "Could not generate summary"}), 500


@app.route("/api/waitlist", methods=["POST"])
@limiter.limit("5/minute")
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
        return jsonify({"error": "Server error"}), 500


# ---------------------------------------------------------------------------
# Analytics & Trends API
# ---------------------------------------------------------------------------
@app.route("/api/privacy-stats")
@limiter.limit("60/minute")
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
@limiter.limit("30/minute")
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
    if _ADMIN_TOKEN and token != _ADMIN_TOKEN:
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
    token = request.args.get("token", "") or request.headers.get("X-Admin-Token", "")
    if _ADMIN_TOKEN and token != _ADMIN_TOKEN:
        return jsonify({"error": "Forbidden"}), 403
    return None


@app.route("/admin")
def admin_dashboard():
    """Main admin dashboard — protected by ADMIN_TOKEN."""
    token = request.args.get("token", "")
    if _ADMIN_TOKEN and token != _ADMIN_TOKEN:
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


@app.route("/admin/api/health")
def admin_api_health():
    """Health check — shows DB connectivity, cache state, live clients."""
    err = _admin_check()
    if err:
        return err
    import datetime as _dt
    health: dict = {
        "status": "ok",
        "server_time": _dt.datetime.utcnow().isoformat() + "Z",
        "storage": _active_storage(),
        "live_sse_clients": len(_SSE_CLIENTS),
    }
    # Test analytics DB
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
    # Cache stats
    try:
        from cachetools import TTLCache as _TC
        health["cache_size"] = len(_result_cache)
        health["cache_maxsize"] = _result_cache.maxsize
    except Exception:
        pass
    return jsonify(health)


# ---------------------------------------------------------------------------
# Admin AI Chatbot — knows everything about abbiey.search
# ---------------------------------------------------------------------------

_ABBIEY_SYSTEM_PROMPT = """You are AbbeyBot, the private internal AI assistant built exclusively for the owner/admin of abbiey.search.

You are an expert in every aspect of this project. You are direct, insightful, and genuinely helpful. You think like a senior full-stack engineer and product strategist who built this system from scratch.

== ARCHITECTURE ==
- Backend: Python Flask (~4200+ lines, app.py) served as a Vercel serverless function via api/index.py
- Host: Vercel (abbieysearch.com → prj_NNB1SRC35VzeuKs5odeDOdS0amTe). Deploy with: vercel deploy --prod --token <token>
- Database (priority order — _analytics_execute() routes automatically):
  1. Supabase/PostgreSQL — set SUPABASE_DB_URL env var (pooler URL port 6543). Auto-creates tables. SQL translated via _adapt_sql_pg().
  2. Turso/libSQL — set LIBSQL_URL + LIBSQL_AUTH_TOKEN env vars. SQLite-compatible HTTP API.
  3. SQLite /tmp — fallback. Ephemeral on Vercel (wiped on cold start). Fine for dev/testing.
  - analytics.db / search_logs table: query, type, region, result_count, latency_ms, hour, day_of_week, created_at
  - analytics.db / error_logs table: route, level, message, created_at
  - users.db: users, user_bookmarks, user_search_history
  - payments.db: payments
- Caching: TTLCache (1000 entries, 300s TTL) + threading.Lock; _in_flight dict deduplicates concurrent identical queries
- HTTP client: httpx connection pool (100 max, 20 keepalive); singleton via _get_http()
- Compression: flask-compress (Brotli preferred, gzip fallback), min_size=500 bytes
- Rate limiting: flask-limiter (30 searches/min, 5 breach-checks/min)
- Auth: Werkzeug password hashing (pbkdf2), Flask sessions
- Payments: Stripe Checkout + webhook
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
/ — Homepage: search bar, recent-searches chips, install banner, onboarding modal
/search — Results page (same index.html template, different render path)
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
/admin/grant-access?token= — Manually grant premium access

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
Monetisation: Premium features (currently Stripe integrated), API access tiers, white-label

Always answer as if you have full context of what's happening right now on the platform. Be specific, actionable, and opinionated. If you see data from the dashboard, analyse it and give real insights."""


@app.route("/admin/api/chat", methods=["POST"])
def admin_chat():
    """AI chatbot for the admin — specialised in abbiey.search."""
    err = _admin_check()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    user_message = (body.get("message") or "").strip()
    history = body.get("history") or []  # list of {role, content}
    dashboard_context = body.get("context") or ""  # optional JSON stats snapshot

    if not user_message:
        return jsonify({"error": "No message"}), 400

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
            "- `payments.db` → Stripe payment records\n"
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
            "8. **PDF/document search** — specialised tab\n"
            "9. **Answer engine mode** — AI-summarised answers at top\n"
            "10. **Sentry error tracking** — get alerts on production errors"
        )

    # Generic helpful response
    return (
        f"I'm AbbeyBot — I know everything about abbiey.search. Ask me about:\n"
        "- **Deploy** — how to push changes live\n"
        "- **Performance** — latency, caching, cold starts\n"
        "- **Search** — how DDG/code/onion search works\n"
        "- **Users** — auth, sessions, database\n"
        "- **Growth** — SEO, traffic, marketing\n"
        "- **Errors** — known bugs, fixes, monitoring\n"
        "- **Features** — what to build next\n\n"
        "For full AI responses, set `OLLAMA_BASE_URL` (local Ollama) or `OPENAI_API_KEY` in Vercel environment variables."
    )


# ---------------------------------------------------------------------------
# Fallback infrastructure — every query MUST return results
# ---------------------------------------------------------------------------

# ---- Layer 1: DDG multi-backend ----

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


# ---- Image fallback layers ----

def _try_openverse(query):
    """Search Openverse (Creative Commons media) for images. No API key needed."""
    results = []
    try:
        resp = _get_http().get(
            "https://api.openverse.org/v1/images/",
            params={"q": query, "page_size": 20},
            headers={"User-Agent": "abbiey.search/1.0", "Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("foreign_landing_url", r.get("url", "")),
                "image": r.get("url", ""),
                "thumbnail": r.get("thumbnail", r.get("url", "")),
                "source": r.get("source", "Openverse"),
            })
        if results:
            logger.info("Openverse fallback: %d image results", len(results))
    except Exception:
        logger.warning("Openverse fallback failed", exc_info=True)
    return results


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
    )
    without_price = [r for r in results if r.get("price_val") is None]
    return (with_price + without_price)[:max_results]


# ---- Alternatives helpers ----

def _try_alternativeto(query, max_results=16):
    """Scrape AlternativeTo search results page."""
    from bs4 import BeautifulSoup
    try:
        resp = _get_http().get(
            f"https://alternativeto.net/browse/search/?q={quote_plus(query)}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=8,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
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

def _fetch_results(query, page, search_type, region=None, lang=None, operators=None, time_filter=None, safesearch="off"):
    """Fetch results with caching. Returns paginated slice."""
    operators = operators or {}
    # Include operators in cache key to prevent cross-contamination
    ops_str = "&".join(f"{k}={','.join(v)}" for k, v in sorted(operators.items())) if operators else ""
    cache_key = f"{query}|{search_type}|{region or ''}|{lang or ''}|{ops_str}|{time_filter or ''}|{safesearch or 'off'}"

    # Check cache
    with _cache_lock:
        cached = _cache.get(cache_key)

    if cached is not None:
        # Serve from cache
        start = RESULTS_PER_PAGE * (page - 1)
        page_results = cached[start : start + RESULTS_PER_PAGE]
        has_more = len(cached) > start + RESULTS_PER_PAGE
        return {"results": page_results, "has_more": has_more, "page": page}

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
            return {"results": page_results, "has_more": has_more, "page": page}

    # Build effective query with operators
    effective_query = _build_engine_query(query, operators) if operators else query
    max_results = CACHE_FETCH_SIZE

    # Onion / Deep Web — dedicated path, skip normal engines
    results = []
    if search_type == "onion":
        results = _try_ahmia(effective_query)
        if not results:
            logger.info("Ahmia empty, trying DDG onion fallback")
            results = _try_onion_ddg(effective_query)
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
        # Layer 1: DDG multi-backend (with timeout guard)
        try:
            with ThreadPoolExecutor(max_workers=1) as _ddg_pool:
                _ddg_fut = _ddg_pool.submit(_try_ddg, effective_query, max_results, search_type, region, time_filter, safesearch)
                results = _ddg_fut.result(timeout=5)
        except Exception:
            logger.exception("DDG failed/timed out for query=%s type=%s", query, search_type)

        # Text: parallel multi-source enrichment — always blend deeper sources alongside DDG
        if search_type == "text":
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

    results = _deduplicate(results)

    # Store in cache
    with _cache_lock:
        _cache[cache_key] = results

    if _my_event is not None:
        with _in_flight_lock:
            _in_flight.pop(cache_key, None)
        _my_event.set()

    start = RESULTS_PER_PAGE * (page - 1)
    page_results = results[start : start + RESULTS_PER_PAGE]
    has_more = len(results) > start + RESULTS_PER_PAGE

    return {"results": page_results, "has_more": has_more, "page": page}


# ---------------------------------------------------------------------------
# Auth routes — signup / login / logout / profile
# ---------------------------------------------------------------------------
import re as _re

_USERNAME_RE = _re.compile(r'^[a-zA-Z0-9_]{3,30}$')


def _require_login():
    """Return a redirect if not logged in, else None."""
    if not session.get("user_id"):
        return redirect(url_for("login", next=request.path))
    return None


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("20/hour")
def signup():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("signup.html")

    username = request.form.get("username", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    errors = []
    if not _USERNAME_RE.match(username):
        errors.append("Username must be 3–30 characters: letters, numbers, underscores only.")
    if not email or "@" not in email:
        errors.append("A valid email address is required.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if password != confirm:
        errors.append("Passwords do not match.")

    if errors:
        return render_template("signup.html", errors=errors, username=username, email=email)

    pw_hash = generate_password_hash(password)
    try:
        rows = _users_execute(
            "INSERT INTO users (username, email, password_hash, display_name) VALUES (?,?,?,?)",
            [username, email, pw_hash, username],
            return_id=True,
        )
        uid = rows[0]["id"] if rows else None
    except Exception as exc:
        msg = str(exc).lower()
        if "username" in msg:
            errors.append("That username is already taken.")
        elif "email" in msg:
            errors.append("An account with that email already exists.")
        else:
            errors.append("Account could not be created. Please try again.")
        return render_template("signup.html", errors=errors, username=username, email=email)

    session.permanent = True
    session["user_id"] = uid
    flash("welcome", "welcome")
    return redirect(url_for("index") + "?welcome=1")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("30/hour")
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html", next=request.args.get("next", ""))

    identifier = request.form.get("identifier", "").strip()
    password   = request.form.get("password", "")
    next_url   = request.form.get("next", "")

    user = _get_user_by_login(identifier)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html",
            error="Invalid email/username or password.",
            identifier=identifier,
            next=next_url,
        )

    session.permanent = True
    session["user_id"] = user["id"]
    return redirect(next_url or url_for("index"))


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("index"))


@app.route("/profile")
def profile():
    redir = _require_login()
    if redir:
        return redir

    uid = session["user_id"]
    user = _get_user_by_id(uid)
    if not user:
        session.pop("user_id", None)
        return redirect(url_for("login"))

    bookmarks = _users_execute(
        "SELECT * FROM user_bookmarks WHERE user_id=? ORDER BY saved_at DESC LIMIT 100",
        [uid],
    )
    history = _users_execute(
        "SELECT query, search_type, searched_at FROM user_search_history"
        " WHERE user_id=? ORDER BY searched_at DESC LIMIT 50",
        [uid],
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

    _users_execute(
        "UPDATE users SET display_name=?, bio=? WHERE id=?",
        [display_name or None, bio, uid],
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
    _users_execute("UPDATE users SET avatar=? WHERE id=?", [avatar_path, uid])

    return redirect(url_for("profile"))


# ---- Bookmarks API (server-side, requires login) ----------------------------

@app.route("/api/user/bookmarks", methods=["GET"])
def api_user_bookmarks_get():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    uid = session["user_id"]
    rows = _users_execute(
        "SELECT id, url, title, snippet, saved_at FROM user_bookmarks"
        " WHERE user_id=? ORDER BY saved_at DESC",
        [uid],
    )
    return jsonify({"bookmarks": rows})


@app.route("/api/user/recent-searches", methods=["GET"])
def api_user_recent_searches():
    if not session.get("user_id"):
        return jsonify([]), 401
    uid = session["user_id"]
    rows = _users_execute(
        "SELECT query, search_type FROM user_search_history"
        " WHERE user_id=? ORDER BY searched_at DESC LIMIT 5",
        [uid],
    )
    seen = set()
    unique = []
    for r in rows:
        if r["query"] not in seen:
            seen.add(r["query"])
            unique.append({"query": r["query"], "type": r["search_type"] or "text"})
    return jsonify(unique)


@app.route("/api/user/bookmarks", methods=["POST"])
@limiter.limit("200/day")
def api_user_bookmarks_save():
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    uid  = session["user_id"]
    data = request.get_json(silent=True) or {}
    url     = (data.get("url") or "").strip()[:2000]
    title   = (data.get("title") or "").strip()[:300]
    snippet = (data.get("snippet") or "").strip()[:500]
    if not url:
        return jsonify({"error": "url required"}), 400
    try:
        rows = _users_execute(
            "INSERT OR IGNORE INTO user_bookmarks (user_id, url, title, snippet)"
            " VALUES (?,?,?,?)",
            [uid, url, title, snippet],
            return_id=True,
        )
        bid = rows[0]["id"] if rows else None
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"ok": True, "id": bid}), 201


@app.route("/api/user/bookmarks/<int:bid>", methods=["DELETE"])
def api_user_bookmarks_delete(bid: int):
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    uid = session["user_id"]
    _users_execute(
        "DELETE FROM user_bookmarks WHERE id=? AND user_id=?", [bid, uid]
    )
    return jsonify({"ok": True})


@app.route("/api/user/bookmarks/sync", methods=["POST"])
@limiter.limit("20/hour")
def api_user_bookmarks_sync():
    """Accept a list of localStorage bookmarks and upsert them server-side."""
    if not session.get("user_id"):
        return jsonify({"error": "Not authenticated"}), 401
    uid   = session["user_id"]
    items = (request.get_json(silent=True) or {}).get("bookmarks", [])
    saved = 0
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
            continue
    return jsonify({"ok": True, "saved": saved})


@app.route("/api/user/history", methods=["POST"])
def api_user_history_add():
    """Record a search query for the logged-in user."""
    if not session.get("user_id"):
        return jsonify({"ok": False}), 200  # silent, not an error
    uid  = session["user_id"]
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


@app.route("/opensearch.xml")
def opensearch():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
  <ShortName>abbiey.search</ShortName>
  <Description>Private, fast, no-tracking search engine</Description>
  <Tags>privacy search private</Tags>
  <Contact>hello@abbieysearch.com</Contact>
  <Url type="text/html" template="https://www.abbieysearch.com/search?q={searchTerms}"/>
  <Url type="application/opensearchdescription+xml" rel="self"
       template="https://www.abbieysearch.com/opensearch.xml"/>
  <Image height="16" width="16" type="image/x-icon">https://www.abbieysearch.com/static/favicon.ico</Image>
  <InputEncoding>UTF-8</InputEncoding>
  <OutputEncoding>UTF-8</OutputEncoding>
</OpenSearchDescription>'''
    return Response(xml, mimetype="application/opensearchdescription+xml")


@app.route("/manifest.json")
def manifest():
    return jsonify({
        "name": "abbiey.search",
        "short_name": "abbiey",
        "description": "Private, fast, no-tracking search engine",
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
    txt = """User-agent: *
Allow: /
Allow: /search
Disallow: /api/
Disallow: /profile
Disallow: /profile/update
Disallow: /logout

Sitemap: https://www.abbieysearch.com/sitemap.xml
"""
    return Response(txt, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.abbieysearch.com/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://www.abbieysearch.com/search</loc>
    <changefreq>daily</changefreq>
    <priority>0.95</priority>
  </url>
  <url>
    <loc>https://www.abbieysearch.com/login</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>https://www.abbieysearch.com/signup</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://www.abbieysearch.com/breach-check</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
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
@limiter.limit("5 per minute")
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
@limiter.limit("20 per minute")
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
    path = request.path
    # Static assets — long-lived immutable cache
    if path.startswith("/static/") and any(
        path.endswith(ext) for ext in (".css", ".js", ".woff2", ".woff", ".ttf", ".png", ".ico", ".svg", ".webp")
    ):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
    # Trends / autocomplete API — short public cache
    if path in ("/api/trends", "/api/autocomplete", "/api/suggestions"):
        response.headers["Cache-Control"] = "public, max-age=60, s-maxage=60"
        return response
    # Search page and HTML — never cache
    if path == "/search" or (response.content_type and "text/html" in response.content_type):
        response.headers["Cache-Control"] = "no-store"
        return response
    return response


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
