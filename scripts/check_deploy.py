#!/usr/bin/env python3
"""
check_deploy.py — Deployment drift detector for abbiey.search

Compares:
  1. Local git HEAD
  2. GitHub remote HEAD (via API)
  3. Live site template fingerprint (CSS class names + deploy-hash meta)

Exits 0 if all in sync, 1 if drift detected.
"""

import re
import subprocess
import sys
import urllib.request
import urllib.error
import json

LIVE_URL   = "https://www.abbieysearch.com"
GITHUB_API = "https://api.github.com/repos/abbieymatthewslol/abbiey-search-engine-2/commits/master"
REPO_ROOT  = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"]
).decode().strip()

# CSS class names that ONLY exist in the current (new) templates.
# If these are absent from the live page, old templates are still deployed.
TEMPLATE_FINGERPRINTS = {
    "/signup": [
        "page-auth",
        "abbiey-auth-main",
        "auth-panel",
        "auth-back-search",
        "auth-container",
        "auth-field",
    ],
    "/login": [
        "page-auth",
        "abbiey-auth-main",
        "auth-panel",
        "auth-back-search",
        "auth-container",
        "auth-field",
    ],
}

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def symbol(ok): return f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"

def get_local_hash() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT
    ).decode().strip()

def get_github_hash():
    try:
        req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "check-deploy"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            return data["sha"]
    except Exception as e:
        print(f"  {YELLOW}⚠ Could not reach GitHub API: {e}{RESET}")
        return None

def fetch_html(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "check-deploy/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  {YELLOW}⚠ Could not reach {url}: {e}{RESET}")
        return ""

def get_deployed_hash(html):
    match = re.search(r'<meta name="deploy-hash" content="([^"]+)"', html)
    return match.group(1) if match else None

def check_template_fingerprint(path, html):
    """Return (ok, missing) — ok=True if all fingerprint classes found."""
    classes = TEMPLATE_FINGERPRINTS.get(path, [])
    missing = [c for c in classes if c not in html]
    return len(missing) == 0, missing

def short(h, n=7):
    return h[:n] if h else "unknown"

def main():
    print(f"\n{BOLD}🔍 abbiey.search — Deployment Drift Check{RESET}")
    print("─" * 45)

    local_hash  = get_local_hash()
    github_hash = get_github_hash()

    local_s  = short(local_hash)
    github_s = short(github_hash)
    github_ok = bool(github_hash and github_hash.startswith(local_s))

    print(f"  Local HEAD    {local_s}")
    print(f"  GitHub master {github_s}  {symbol(github_ok)}")
    print()

    # --- Template fingerprint checks ---
    print(f"  {BOLD}Template checks (live site){RESET}")
    all_templates_ok = True
    for path, _ in TEMPLATE_FINGERPRINTS.items():
        html = fetch_html(LIVE_URL + path)
        ok, missing = check_template_fingerprint(path, html)
        deployed_hash = get_deployed_hash(html)
        hash_s = short(deployed_hash) if deployed_hash else f"{YELLOW}no hash{RESET}"
        status = symbol(ok)
        label = f"{LIVE_URL}{path}"
        if ok:
            print(f"    {status} {label}  (hash: {hash_s})")
        else:
            print(f"    {status} {label}")
            print(f"       Missing CSS classes: {', '.join(missing)}")
            print(f"       → Old template still live — trigger a Vercel/Render redeploy.")
            all_templates_ok = False

    print()
    drift = False

    if not github_ok:
        print(f"{RED}  ✗ Local commits NOT pushed to GitHub.{RESET}")
        print(f"    Run: git push origin master")
        drift = True

    if not all_templates_ok:
        print(f"{RED}  ✗ Live templates are stale — repo changes not deployed yet.{RESET}")
        drift = True

    if not drift:
        print(f"{GREEN}  ✓ All in sync — live site is running the latest templates.{RESET}")

    print()
    sys.exit(1 if drift else 0)

if __name__ == "__main__":
    main()
