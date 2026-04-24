#!/usr/bin/env python3
"""
restore_vercel_env.py — Push all env vars from .env / .env.local to Vercel.

Never manually re-enter environment variables again.

Usage:
    python scripts/restore_vercel_env.py           # preview what will be pushed
    python scripts/restore_vercel_env.py --apply   # actually push to Vercel
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

REPO_ROOT = Path(__file__).parent.parent

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
target_env = "production"
for arg in sys.argv[1:]:
    if arg.startswith("--env="):
        target_env = arg.split("=", 1)[1]
    elif arg in ("--env", "--environment") and sys.argv.index(arg) + 1 < len(sys.argv):
        target_env = sys.argv[sys.argv.index(arg) + 1]

print(f"\n{BOLD}Vercel Env Restore{RESET}")
print(f"  Mode:        {'APPLY (will write to Vercel)' if apply_mode else 'DRY RUN (use --apply to write)'}")
print(f"  Environment: {target_env}")
print(f"  Project:     {VERCEL_PROJECT_ID}")

# ─── Load local env ───────────────────────────────────────────────────────────
local_env = load_env(REPO_ROOT / ".env")
local_env.update(load_env(REPO_ROOT / ".env.local"))

if not local_env:
    print(f"\n{RED}ERROR: No .env or .env.local file found in {REPO_ROOT}{RESET}")
    print("Create a .env file with your secrets first.")
    sys.exit(1)

print(f"\n  Found {len(local_env)} variables in .env / .env.local")

# Filter out skip vars and empty values
to_push = {
    k: v for k, v in local_env.items()
    if k not in SKIP_VARS
    and v
    and not v.startswith("generate_")
    and not v.startswith("your_")
    and not v.startswith("INSERT_")
    and not v.startswith("<")
}

print(f"  Pushing {len(to_push)} non-placeholder variables")

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
    if key in PUBLIC_VARS:
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
    print(f"\n{GREEN}All env vars pushed successfully!{RESET}")
    print(f"\nRedeploy Vercel to pick up changes:")
    print(f"  vercel deploy --prod")
    print(f"  # or: git commit --allow-empty -m 'chore: redeploy' && git push origin master")
