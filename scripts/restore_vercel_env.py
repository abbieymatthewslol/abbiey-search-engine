#!/usr/bin/env python3
"""
restore_vercel_env.py — Push all env vars from .env / .env.local to Vercel.

Never manually re-enter environment variables again.

Usage:
    python scripts/restore_vercel_env.py           # preview what will be pushed
    python scripts/restore_vercel_env.py --apply   # actually push to Vercel
    python scripts/restore_vercel_env.py --all-targets  # push every key to production+preview+development
    python scripts/restore_vercel_env.py --no-normalize # skip SITE_URL / Supabase auto-fixes
    python scripts/restore_vercel_env.py --env production  # default
    python scripts/restore_vercel_env.py --env preview     # also push to preview
    python scripts/restore_vercel_env.py --env development # also push to development

What it does:
    1. Reads all vars from .env (then .env.local overrides)
    2. Shows a diff of what will change (current Vercel value vs local .env value)
    3. With --apply, upserts all vars via the Vercel API (create if missing, update if changed)

Requirements:
    - .env file must exist in repo root (gitignored, never committed)
    - Vercel token at %APPDATA%/com.vercel.cli/Data/auth.json OR in VERCEL_TOKEN env var
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).parent.parent

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from vercel_env_normalize import normalize_vercel_env_vars  # noqa: E402

VERCEL_PROJECT_ID = "prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b"
VERCEL_TEAM_ID    = "team_YeguIG4NHm4Kp0Jf5AbOwgFN"

# These vars are safe to push to all environments (non-secret)
# Everything else defaults to "production" only unless --env is specified
PUBLIC_VARS = {
    "SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
    "SITE_URL",
    "CORS_ALLOWED_ORIGINS",
    "BROWSERBASE_PROJECT_ID",
    "POSTGRES_HOST",
    "POSTGRES_USER",
    "POSTGRES_DATABASE",
    "NEXT_PUBLIC_SENTRY_DSN",
    "SENTRY_ORG",
    "SENTRY_PROJECT",
}

# Skip these — they're Vercel-internal or should never be pushed
SKIP_VARS = {
    "PORT",          # Vercel sets this
    "NODE_ENV",      # Vercel sets this
    "VERCEL",        # Vercel sets this
    "VERCEL_ENV",    # Vercel sets this
    "VERCEL_TOKEN",  # local/CI only — never store on the project
    "VERCEL_OIDC_TOKEN",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def load_env(path):
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

def validate_push_payload(env: dict) -> list[str]:
    """Return fatal error strings if required production variables are missing or inconsistent."""
    errs: list[str] = []
    sb = (env.get("SUPABASE_URL") or "").strip().rstrip("/")
    if not sb:
        errs.append("SUPABASE_URL is required")
    if not sb.lower().startswith("https://"):
        errs.append("SUPABASE_URL must use https://")
    db = (env.get("SUPABASE_DB_URL") or env.get("DATABASE_URL") or "").strip()
    if not db:
        errs.append("SUPABASE_DB_URL (or DATABASE_URL) is required for Vercel")
    else:
        low = db.lower()
        if "pooler.supabase.com" not in low:
            errs.append("SUPABASE_DB_URL must use the Supabase transaction pooler (pooler.supabase.com:6543)")
        try:
            u = db.replace("postgresql+psycopg2://", "postgresql://", 1)
            p = urlparse(u)
            port = p.port or 5432
            user = unquote((p.username or "").strip())
            host = (p.hostname or "").lower()
        except Exception:
            port, user, host = 0, "", ""
        if port != 6543 and "pooler.supabase.com" in host:
            errs.append("SUPABASE_DB_URL must use port 6543 for the transaction pooler on Vercel")
        if "pooler.supabase.com" in host and port == 6543 and user == "postgres":
            errs.append("SUPABASE_DB_URL must use postgres.<project-ref> as the DB user (not bare postgres) on port 6543")
    np_url = (env.get("NEXT_PUBLIC_SUPABASE_URL") or "").strip().rstrip("/")
    if sb and np_url and np_url.lower() != sb.lower():
        errs.append("NEXT_PUBLIC_SUPABASE_URL must exactly match SUPABASE_URL")
    anon = (env.get("SUPABASE_ANON_KEY") or "").strip()
    np_anon = (env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or "").strip()
    if anon and np_anon and anon != np_anon:
        errs.append("NEXT_PUBLIC_SUPABASE_ANON_KEY must match SUPABASE_ANON_KEY when both are set")
    site = (env.get("SITE_URL") or "").strip().rstrip("/")
    if not site:
        errs.append("SITE_URL is required (https://abbieysearch.com)")
    elif site.lower() != "https://abbieysearch.com":
        errs.append("SITE_URL must be https://abbieysearch.com for this automation path")
    return errs


def vercel_request(method, path, token, body=None):
    url = f"https://api.vercel.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
    except Exception as e:
        return None, {"error": str(e)}

# ─── Parse args ───────────────────────────────────────────────────────────────
apply_mode = "--apply" in sys.argv
all_targets = "--all-targets" in sys.argv
no_normalize = "--no-normalize" in sys.argv
target_env = "production"
for arg in sys.argv[1:]:
    if arg.startswith("--env="):
        target_env = arg.split("=", 1)[1]
    elif arg in ("--env", "--environment") and sys.argv.index(arg) + 1 < len(sys.argv):
        target_env = sys.argv[sys.argv.index(arg) + 1]

print(f"\n{BOLD}Vercel Env Restore{RESET}")
print(f"  Mode:        {'APPLY (will write to Vercel)' if apply_mode else 'DRY RUN (use --apply to write)'}")
print(f"  Environment: {target_env}")
print(f"  All targets: {all_targets}")
print(f"  Normalize:   {not no_normalize}")
print(f"  Project:     {VERCEL_PROJECT_ID}")

# ─── Load local env ───────────────────────────────────────────────────────────
local_env = load_env(REPO_ROOT / ".env")
local_env.update(load_env(REPO_ROOT / ".env.local"))

if not local_env:
    print(f"\n{RED}ERROR: No .env or .env.local file found in {REPO_ROOT}{RESET}")
    print("Create a .env file with your secrets first.")
    sys.exit(1)

print(f"\n  Found {len(local_env)} variables in .env / .env.local")

working = dict(local_env)
if not no_normalize:
    working, norm_notes = normalize_vercel_env_vars(working, enforce_site_url=True)
    for note in norm_notes:
        print(f"  {CYAN}normalize:{RESET} {note}")

# Filter out skip vars and empty values
to_push = {
    k: v for k, v in working.items()
    if k not in SKIP_VARS
    and v
    and not v.startswith("generate_")
    and not v.startswith("your_")
    and not v.startswith("INSERT_")
    and not v.startswith("<")
}

print(f"  Pushing {len(to_push)} non-placeholder variables")

fatal = validate_push_payload(to_push)
if fatal:
    print(f"\n{RED}Validation failed (fix .env or allow normalize):{RESET}")
    for e in fatal:
        print(f"  {RED}•{RESET} {e}")
    sys.exit(1)

# ─── Get Vercel token ──────────────────────────────────────────────────────────
vercel_token = os.environ.get("VERCEL_TOKEN", "")
if not vercel_token:
    auth_path = Path(os.environ.get("APPDATA", "")) / "com.vercel.cli" / "Data" / "auth.json"
    auth_path_exists = False
    try:
        auth_path_exists = auth_path.exists()
    except PermissionError:
        print(f"  {YELLOW}Warning: access denied reading {auth_path}; set VERCEL_TOKEN instead{RESET}")
    except OSError as exc:
        print(f"  {YELLOW}Warning: could not inspect {auth_path}: {exc}{RESET}")

    if auth_path_exists:
        try:
            vercel_token = json.loads(auth_path.read_text()).get("token", "")
        except PermissionError:
            print(f"  {YELLOW}Warning: access denied loading {auth_path}; set VERCEL_TOKEN instead{RESET}")
        except Exception:
            pass

if not vercel_token:
    print(f"\n{RED}ERROR: No Vercel token found.{RESET}")
    print("Either:")
    print("  1. Run: npx vercel login   (saves to %APPDATA%\\com.vercel.cli\\Data\\auth.json)")
    print("  2. Set VERCEL_TOKEN environment variable")
    sys.exit(1)

print(f"  Vercel token: found")

# ─── Get current Vercel env vars (to show diff) ────────────────────────────────
print(f"\n{BOLD}Fetching current Vercel env vars...{RESET}")
status, current_data = vercel_request(
    "GET",
    f"/v9/projects/{VERCEL_PROJECT_ID}/env?teamId={VERCEL_TEAM_ID}&decrypt=true",
    vercel_token
)

current_vars = {}
current_ids = {}
if status == 200:
    for item in current_data.get("envs", []):
        key = item["key"]
        current_vars[key] = item.get("value", "")
        current_ids[key] = item["id"]
    print(f"  Found {len(current_vars)} existing env vars on Vercel")
elif status is None:
    print(f"  {YELLOW}Warning: could not fetch current vars ({current_data.get('error')}){RESET}")
else:
    print(f"  {YELLOW}Warning: Vercel API returned {status}{RESET}")

# ─── Show diff ────────────────────────────────────────────────────────────────
print(f"\n{BOLD}Changes to be made:{RESET}")

new_vars = []
update_vars = []
unchanged_vars = []

for key, val in sorted(to_push.items()):
    if key not in current_vars:
        new_vars.append((key, val))
    elif current_vars[key] != val:
        update_vars.append((key, val, current_vars[key]))
    else:
        unchanged_vars.append(key)

for key, val in new_vars:
    display_val = val[:40] + "..." if len(val) > 40 else val
    print(f"  {GREEN}+ {key:<45}{RESET} = {display_val}")

for key, val, old_val in update_vars:
    display_new = val[:30] + "..." if len(val) > 30 else val
    display_old = old_val[:30] + "..." if len(old_val) > 30 else old_val
    print(f"  {YELLOW}~ {key:<45}{RESET} {display_old!r} -> {display_new!r}")

if unchanged_vars:
    print(f"\n  {len(unchanged_vars)} vars unchanged (skipping)")

if not new_vars and not update_vars:
    print(f"\n  {GREEN}Everything is already up to date!{RESET}")
    sys.exit(0)

print(f"\n  {len(new_vars)} to create, {len(update_vars)} to update")

# ─── Apply ─────────────────────────────────────────────────────────────────────
if not apply_mode:
    print(f"\n{CYAN}DRY RUN complete. Run with --apply to push changes to Vercel.{RESET}")
    sys.exit(0)

print(f"\n{BOLD}Applying changes to Vercel ({target_env})...{RESET}")

errors = []
successes = 0

def push_var(key, val, existing_id=None):
    global successes
    # Determine target environments
    if all_targets:
        envs = ["production", "preview", "development"]
    elif key in PUBLIC_VARS:
        envs = ["production", "preview", "development"]
    else:
        envs = [target_env]

    payload = {
        "key": key,
        "value": val,
        "type": "encrypted",
        "target": envs,
    }

    if existing_id:
        # Update existing
        status, resp = vercel_request(
            "PATCH",
            f"/v9/projects/{VERCEL_PROJECT_ID}/env/{existing_id}?teamId={VERCEL_TEAM_ID}",
            vercel_token,
            payload
        )
    else:
        # Create new
        status, resp = vercel_request(
            "POST",
            f"/v9/projects/{VERCEL_PROJECT_ID}/env?teamId={VERCEL_TEAM_ID}",
            vercel_token,
            payload
        )

    if status in (200, 201):
        print(f"  {GREEN}✓{RESET}  {key}")
        successes += 1
    else:
        err = resp.get("error", {}).get("message", str(resp))
        print(f"  {RED}✗{RESET}  {key}: {err}")
        errors.append(f"{key}: {err}")

for key, val in new_vars:
    push_var(key, val)

for key, val, _ in update_vars:
    push_var(key, val, existing_id=current_ids.get(key))

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{BOLD}Done.{RESET}")
print(f"  {successes} succeeded, {len(errors)} failed")

if errors:
    print(f"\n{RED}Errors:{RESET}")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)
else:
    production_branch = (os.environ.get("ABBIEY_PRODUCTION_BRANCH") or "main").strip() or "main"
    print(f"\n{GREEN}All env vars pushed successfully!{RESET}")
    print(f"\nRedeploy Vercel to pick up changes:")
    print(f"  vercel deploy --prod")
    print(f"  # or: git commit --allow-empty -m 'chore: redeploy' && git push origin {production_branch}")
