#!/usr/bin/env python3
"""
health_check.py — Verify every production integration in one command.

Usage:
    python scripts/health_check.py
    python scripts/health_check.py --quiet   # exit 1 if any check fails

Checks:
    1. Environment variables present
    2. Supabase DB connectivity (IPv4 forced)
    3. Supabase Auth API — project active, Google OAuth enabled, redirect URLs
    4. Live site response (www.abbieysearch.com)
    5. Live site /admin/api/health endpoint
    6. Vercel latest deployment (requires VERCEL_TOKEN or local auth.json)
"""

import base64
import json
import os
import socket
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Windows cp1252 consoles cannot print Unicode markers (✓/✗) by default.
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def _jwt_project_ref(token):
    """Decode JWT payload (no signature check) and return the 'ref' field."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("ref", "")
    except Exception:
        return ""

# ─── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg): print(f"  {RED}✗{RESET}  {msg}"); FAILURES.append(msg)
def warn(msg): print(f"  {YELLOW}!{RESET}  {msg}")
def info(msg): print(f"  {CYAN}→{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}")

FAILURES = []

# ─── Load .env ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent

def load_env(path):
    """Parse a .env file into a dict (no external deps)."""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        env[key.strip()] = val
    return env

# Load in priority: .env.local overrides .env
env = load_env(REPO_ROOT / ".env")
env.update(load_env(REPO_ROOT / ".env.local"))
# Also check OS environment
for k, v in os.environ.items():
    if k not in env:
        env[k] = v

EXPECTED_REF = (env.get("ABBIEY_SUPABASE_PROJECT_REF") or "xwxscvllmghyogddpmii").strip()

# ─── Check 1: Required environment variables ───────────────────────────────────
header("1. Environment Variables")

REQUIRED_VARS = [
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_DB_URL",
    "SECRET_KEY",
    "ADMIN_TOKEN",
    "SITE_URL",
]

for var in REQUIRED_VARS:
    val = env.get(var, "")
    if not val or val.startswith("generate_") or val.startswith("change-me"):
        if var in ("SECRET_KEY", "ADMIN_TOKEN"):
            warn(f"{var} is placeholder locally — ensure it's set in Vercel")
        else:
            fail(f"{var} missing or placeholder")
    elif var in ("SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        # Project ref is embedded in the JWT payload (base64), not as a literal string
        ref = _jwt_project_ref(val)
        if ref and ref != EXPECTED_REF:
            fail(f"{var} JWT ref is '{ref}' — expected {EXPECTED_REF}")
        elif ref == EXPECTED_REF:
            ok(f"{var} set (JWT ref: {ref} ✓)")
        else:
            ok(f"{var} set (JWT ref not decoded — verify manually)")
    elif var == "SUPABASE_DB_URL":
        need = f"postgres.{EXPECTED_REF}"
        if need not in val:
            fail(f"{var} must include pooler user {need} (set ABBIEY_SUPABASE_PROJECT_REF if using another project)")
        else:
            ok(f"{var} set (correct pooler user)")
    else:
        ok(f"{var} set")

# Check for the deleted project ref creeping back in
for var in REQUIRED_VARS:
    val = env.get(var, "")
    if "xibqrimcvgtxtqkybxaa" in val:
        fail(f"{var} STILL references the DELETED project xibqrimcvgtxtqkybxaa!")

# ─── Check 2: Supabase Database connection ─────────────────────────────────────
header("2. Supabase Database")

db_url = env.get("SUPABASE_DB_URL", "")
if not db_url:
    fail("SUPABASE_DB_URL not set — skipping DB check")
else:
    try:
        import psycopg2

        # Force IPv4 — psycopg2 on Windows/Linux prefers IPv6 but pooler only accepts IPv4
        _orig_getaddrinfo = socket.getaddrinfo
        def _ipv4_only(host, port, family=0, socktype=0, proto=0, flags=0):
            return _orig_getaddrinfo(host, port, socket.AF_INET, socktype, proto, flags)
        socket.getaddrinfo = _ipv4_only

        try:
            conn = psycopg2.connect(db_url, connect_timeout=10)
            cur = conn.cursor()
            cur.execute("SELECT version(), current_database()")
            ver, db_name = cur.fetchone()
            cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            (table_count,) = cur.fetchone()
            conn.close()
            socket.getaddrinfo = _orig_getaddrinfo
        except Exception:
            socket.getaddrinfo = _orig_getaddrinfo
            raise

        ok(f"Connected to '{db_name}' — {ver.split(',')[0]}")
        ok(f"{table_count} public tables found")

    except ImportError:
        warn("psycopg2 not installed — run: pip install psycopg2-binary")
    except Exception as e:
        socket.getaddrinfo = _orig_getaddrinfo
        fail(f"DB connection failed: {e}")

# ─── Check 3: Supabase Auth API ────────────────────────────────────────────────
header("3. Supabase Auth API")

SUPABASE_PROJECT_REF = EXPECTED_REF
SUPABASE_URL = env.get("SUPABASE_URL", f"https://{SUPABASE_PROJECT_REF}.supabase.co")
SUPABASE_ANON_KEY = env.get("SUPABASE_ANON_KEY", "")

# Check the project is reachable
def http_get(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)

# Probe the Supabase project health
status, body = http_get(f"{SUPABASE_URL}/auth/v1/health", {
    "apikey": SUPABASE_ANON_KEY,
})
if status == 200:
    ok(f"Auth API healthy ({SUPABASE_URL})")
elif status is None:
    fail(f"Auth API unreachable: {body}")
else:
    fail(f"Auth API returned {status}: {body[:200]}")

# Try to check OAuth provider via management API (needs PAT)
PAT = ""
try:
    import subprocess
    result = subprocess.run(
        ["powershell", "-Command",
         "(Get-StoredCredential -Target 'Supabase CLI:supabase').GetNetworkCredential().Password"],
        capture_output=True, text=True, timeout=5
    )
    PAT = result.stdout.strip()
except Exception:
    pass

if not PAT:
    PAT = env.get("SUPABASE_ACCESS_TOKEN", "") or env.get("SUPABASE_PAT", "")

if PAT:
    status, body = http_get(
        f"https://api.supabase.com/v1/projects/{SUPABASE_PROJECT_REF}/config/auth",
        {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
    )
    if status == 200:
        try:
            cfg = json.loads(body)
            site_url = cfg.get("site_url", "")
            redirects = cfg.get("uri_allow_list", "")

            if "abbieysearch.com" in site_url:
                ok(f"Site URL: {site_url}")
            else:
                fail(f"Site URL wrong: got '{site_url}', expected abbieysearch.com")

            needed = [
                "abbieysearch.com/auth/confirm",
                "abbieysearch.com/auth/callback",
            ]
            for url in needed:
                if url in redirects:
                    ok(f"Redirect allow list contains: {url}")
                else:
                    fail(f"Redirect allow list MISSING: {url}")

        except Exception as e:
            warn(f"Could not parse auth config: {e}")
    else:
        warn(f"Management API returned {status} — cannot verify OAuth config")
else:
    warn("No Supabase PAT found — skipping auth config verification")
    info("PAT stored in Windows Credential Manager: 'Supabase CLI:supabase'")

# ─── Check 4: Live site ────────────────────────────────────────────────────────
header("4. Live Site")

SITE_URL = env.get("SITE_URL", "https://www.abbieysearch.com")

status, body = http_get(SITE_URL, timeout=15)
if status == 200:
    ok(f"Homepage returns 200 ({SITE_URL})")
    if "abbieysearch" in body.lower() or "search" in body.lower():
        ok("Homepage content looks correct")
    else:
        warn("Homepage response doesn't look right — check content")
elif status in (301, 302):
    ok(f"Homepage redirects ({status})")
elif status == 429:
    warn(f"Homepage rate-limited (429) — site is UP but IP was throttled by Vercel")
elif status is None:
    fail(f"Homepage unreachable: {body}")
else:
    fail(f"Homepage returned {status}")

# Check login page renders with Supabase JS
status, body = http_get(f"{SITE_URL}/login", timeout=15)
if status == 200:
    ok("/login returns 200")
    if "supabase" in body.lower():
        ok("Supabase JS found in /login HTML")
    else:
        warn("Supabase JS not found in /login — OAuth button may not work")
    if "google" in body.lower():
        ok("Google OAuth button found in /login HTML")
    else:
        warn("Google OAuth button not found in /login HTML")
    if "nonce=" in body:
        ok("CSP nonces present in /login HTML")
    else:
        fail("/login HTML has NO nonce= on script tags — CSP will block inline JS!")
elif status == 429:
    warn("/login rate-limited (429) — site is UP, skipping content checks")
elif status is None:
    fail(f"/login unreachable: {body}")
else:
    fail(f"/login returned {status}")

# ─── Check 5: Health endpoint ──────────────────────────────────────────────────
header("5. Admin Health Endpoint")

ADMIN_TOKEN = env.get("ADMIN_TOKEN", "")
if not ADMIN_TOKEN:
    warn("ADMIN_TOKEN not set — skipping /admin/api/health check")
else:
    status, body = http_get(f"{SITE_URL}/admin/api/health?token={ADMIN_TOKEN}", timeout=15)
    if status == 200:
        try:
            health = json.loads(body)
            ok(f"Health endpoint OK: {json.dumps(health, indent=2)}")
        except Exception:
            ok(f"Health endpoint OK (non-JSON): {body[:200]}")
    elif status == 403:
        fail("Health endpoint returned 403 — ADMIN_TOKEN wrong?")
    elif status == 429:
        warn("Health endpoint rate-limited (429) — site is UP")
    elif status is None:
        fail(f"Health endpoint unreachable: {body}")
    else:
        fail(f"Health endpoint returned {status}: {body[:200]}")

# ─── Check 6: Vercel deployment ────────────────────────────────────────────────
header("6. Vercel Deployment")

VERCEL_PROJECT_ID = "prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b"
VERCEL_TEAM_ID = "team_YeguIG4NHm4Kp0Jf5AbOwgFN"

# Try to get Vercel token from local auth.json
vercel_token = env.get("VERCEL_TOKEN", "")
if not vercel_token:
    auth_path = Path(os.environ.get("APPDATA", "")) / "com.vercel.cli" / "Data" / "auth.json"
    if auth_path.exists():
        try:
            auth_data = json.loads(auth_path.read_text())
            vercel_token = auth_data.get("token", "")
        except Exception:
            pass

if not vercel_token:
    warn("No Vercel token found — skipping Vercel check")
    info("Token at: %APPDATA%\\com.vercel.cli\\Data\\auth.json")
else:
    status, body = http_get(
        f"https://api.vercel.com/v6/deployments?projectId={VERCEL_PROJECT_ID}&teamId={VERCEL_TEAM_ID}&limit=1",
        {"Authorization": f"Bearer {vercel_token}"}
    )
    if status == 200:
        try:
            data = json.loads(body)
            deploys = data.get("deployments", [])
            if deploys:
                d = deploys[0]
                state = d.get("state", "unknown")
                url = d.get("url", "")
                created = d.get("createdAt", "")
                meta = d.get("meta", {})
                commit = meta.get("githubCommitSha", "")[:7]
                msg = meta.get("githubCommitMessage", "")

                if state == "READY":
                    ok(f"Latest deployment READY: {url}")
                elif state == "ERROR":
                    fail(f"Latest deployment ERRORED: {url}")
                else:
                    warn(f"Latest deployment state: {state} — {url}")

                if commit:
                    ok(f"Deployed commit: {commit} — {msg[:60]}")
            else:
                warn("No deployments found")
        except Exception as e:
            warn(f"Could not parse Vercel response: {e}")
    else:
        warn(f"Vercel API returned {status}")

# ─── Summary ───────────────────────────────────────────────────────────────────
header("Summary")

if FAILURES:
    print(f"\n{RED}{BOLD}FAILED — {len(FAILURES)} issue(s):{RESET}")
    for f in FAILURES:
        print(f"  • {f}")
    sys.exit(1)
else:
    print(f"\n{GREEN}{BOLD}All checks passed ✓{RESET}")
    sys.exit(0)
