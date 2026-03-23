#!/usr/bin/env python3
"""
check_deploy.py — Deployment drift detector for abbiey.search

Compares:
  1. Local git HEAD
  2. GitHub remote HEAD (via API)
  3. Deployed site's embed commit hash (via <meta name="deploy-hash">)

Exits 0 if all match, 1 if drift is detected.
"""

import re
import subprocess
import sys
import urllib.request
import urllib.error
import json

LIVE_URL   = "https://www.abbieysearch.com"
GITHUB_API = "https://api.github.com/repos/abbieymatthewslol/abbiey-search-engine/commits/master"
REPO_ROOT  = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"]
).decode().strip()

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

def get_deployed_hash(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "check-deploy/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        match = re.search(r'<meta name="deploy-hash" content="([^"]+)"', html)
        return match.group(1) if match else None
    except Exception as e:
        print(f"  {YELLOW}⚠ Could not reach {url}: {e}{RESET}")
        return None

def short(h, n=7):
    return h[:n] if h else "unknown"

def main():
    print(f"\n{BOLD}🔍 abbiey.search — Deployment Drift Check{RESET}")
    print("─" * 45)

    local_hash    = get_local_hash()
    github_hash   = get_github_hash()
    deployed_hash = get_deployed_hash(LIVE_URL)

    local_s    = short(local_hash)
    github_s   = short(github_hash)
    deployed_s = short(deployed_hash) if deployed_hash else f"{YELLOW}not found (old template?){RESET}"

    github_ok   = bool(github_hash and github_hash.startswith(local_s))
    deployed_ok = bool(deployed_hash and local_hash.startswith(deployed_hash))

    print(f"  Local HEAD    {local_s}")
    print(f"  GitHub master {github_s}  {symbol(github_ok)}")
    print(f"  Live site     {deployed_s}  {symbol(deployed_ok)}")
    print()

    drift = False

    if not github_ok:
        print(f"{RED}  ✗ Local commits have NOT been pushed to GitHub.{RESET}")
        print(f"    Run: git push origin master")
        drift = True

    if not deployed_hash:
        print(f"{YELLOW}  ⚠ Live site has no deploy-hash meta tag — old template still served.{RESET}")
        print(f"    → Trigger a manual redeploy on Render/Vercel dashboard.")
        drift = True
    elif not deployed_ok:
        print(f"{RED}  ✗ Live site is BEHIND — Render has not redeployed yet.{RESET}")
        print(f"    GitHub is at {github_s}, live is at {deployed_s}.")
        print(f"    → render.com → your service → Manual Deploy → Deploy latest commit.")
        drift = True

    if not drift:
        print(f"{GREEN}  ✓ All in sync — live site is running the latest code.{RESET}")

    print()
    sys.exit(1 if drift else 0)

if __name__ == "__main__":
    main()
