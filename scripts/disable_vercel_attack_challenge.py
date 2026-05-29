#!/usr/bin/env python3
"""
Turn off Vercel Attack Challenge Mode for the production project.

When enabled, visitors see the "Vercel Security Checkpoint" (HTTP 429) instead of the app.

Requires: VERCEL_TOKEN (Vercel account token with access to the project).
Optional: VERCEL_PROJECT_ID (default: live abbieysearch.com project),
          VERCEL_TEAM_ID or VERCEL_ORG_ID (team slug id, e.g. team_...).

Usage:
  python scripts/disable_vercel_attack_challenge.py
  python scripts/disable_vercel_attack_challenge.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_PROJECT_ID = "prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b"
API = "https://api.vercel.com/v1/security/attack-mode"


def _load_dotenv_defaults() -> None:
    """If VERCEL_TOKEN is unset, fill from repo-root .env (no extra deps)."""
    if os.environ.get("VERCEL_TOKEN"):
        return
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    try:
        raw = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        if key not in (
            "VERCEL_TOKEN",
            "VERCEL_PROJECT_ID",
            "VERCEL_ORG_ID",
            "VERCEL_TEAM_ID",
        ):
            continue
        val = val.strip().strip("'").strip('"')
        os.environ.setdefault(key, val)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the request body only; do not call the API.",
    )
    args = parser.parse_args()

    _load_dotenv_defaults()

    token = (os.environ.get("VERCEL_TOKEN") or "").strip()
    project_id = (os.environ.get("VERCEL_PROJECT_ID") or DEFAULT_PROJECT_ID).strip()
    team_id = (
        os.environ.get("VERCEL_TEAM_ID")
        or os.environ.get("VERCEL_ORG_ID")
        or ""
    ).strip()

    if not token and not args.dry_run:
        print(
            "VERCEL_TOKEN is not set. Create a token at "
            "https://vercel.com/account/tokens then run:\n"
            "  set VERCEL_TOKEN=...   (Windows)\n"
            "  export VERCEL_TOKEN=...  (Unix)",
            file=sys.stderr,
        )
        return 2

    body = json.dumps(
        {"projectId": project_id, "attackModeEnabled": False}
    ).encode("utf-8")

    if args.dry_run:
        print("Would POST", API)
        print("Body:", body.decode())
        if team_id:
            print("Team query:", team_id)
        return 0

    url = API
    if team_id:
        url = f"{API}?teamId={urllib.parse.quote(team_id, safe='')}"

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"Vercel API HTTP {e.code}: {err_body}", file=sys.stderr)
        return 1

    print(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if data.get("attackModeEnabled") is False:
        print("Attack Challenge Mode is now OFF for this project.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
