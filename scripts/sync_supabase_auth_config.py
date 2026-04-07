#!/usr/bin/env python3
"""
Push Site URL + redirect allow list to Supabase Auth via the Management API.

Idempotent: merges with existing uri_allow_list; never removes entries you added manually.

Token resolution (first hit wins):
  1. SUPABASE_ACCESS_TOKEN or SUPABASE_PAT env
  2. ~/.supabase/access-token (Supabase CLI fallback file)
  3. Windows: Credential Manager target "Supabase CLI:supabase" (PowerShell)

Usage (repo root):
  python scripts/sync_supabase_auth_config.py
  python scripts/sync_supabase_auth_config.py --dry-run
  python scripts/sync_supabase_auth_config.py --require-token   # exit 1 if no PAT

Optional — sync Google provider into Supabase (same as Dashboard → Auth → Google):
  Set both SUPABASE_SYNC_GOOGLE_CLIENT_ID and SUPABASE_SYNC_GOOGLE_CLIENT_SECRET in .env
  (use your Web client ID + secret from Google Cloud Console).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_repo_root() / ".env")
    except ImportError:
        pass


def _project_ref_from_supabase_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        raise ValueError("SUPABASE_URL is empty")
    # https://abcdefgh.supabase.co
    m = re.match(r"^https?://([a-z0-9]{20})\.supabase\.co", u, re.I)
    if not m:
        raise ValueError(f"Could not parse project ref from SUPABASE_URL={u!r}")
    return m.group(1).lower()


def _get_management_token() -> str:
    t = (os.environ.get("SUPABASE_ACCESS_TOKEN") or os.environ.get("SUPABASE_PAT") or "").strip()
    if t:
        return t
    home = Path.home()
    fp = home / ".supabase" / "access-token"
    if fp.is_file():
        raw = fp.read_text(encoding="utf-8").strip()
        if raw:
            return raw
    if sys.platform == "win32":
        try:
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-StoredCredential -Target 'Supabase CLI:supabase' -ErrorAction SilentlyContinue)"
                    ".GetNetworkCredential().Password",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            out = (r.stdout or "").strip()
            if out:
                return out
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ""


def _canonical_site_url() -> str:
    s = (os.environ.get("SITE_URL") or os.environ.get("CANONICAL_URL") or "").strip().rstrip("/")
    if s:
        return s
    return "https://www.abbieysearch.com"


def _default_redirect_urls() -> list[str]:
    """Full redirect URLs Supabase must allow (OAuth, email links, previews)."""
    extra = (os.environ.get("AUTH_EXTRA_REDIRECT_URLS") or "").strip()
    extra_parts = [p.strip() for p in re.split(r"[\n,]+", extra) if p.strip()]

    site = _canonical_site_url()
    bases: list[str] = [
        "https://www.abbieysearch.com",
        "https://abbieysearch.com",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "https://search-engine-abbieys-projects.vercel.app",
    ]
    if site not in bases:
        bases.insert(0, site)

    paths = (
        "/auth/confirm",
        "/auth/callback",
        "/login",
    )
    out: list[str] = []
    for b in bases:
        b = b.rstrip("/")
        for p in paths:
            out.append(b + p)

    # Wildcards documented for Vercel preview deployments (Supabase accepts these patterns)
    out.extend(
        [
            "https://search-engine-abbieys-projects.vercel.app/**",
            "https://search-*-engine-abbieys-projects.vercel.app/**",
        ]
    )

    vercel = (os.environ.get("VERCEL_URL") or "").strip().rstrip("/")
    if vercel and not vercel.startswith("http"):
        vercel = "https://" + vercel
    if vercel:
        for p in paths:
            u = vercel + p
            if u not in out:
                out.append(u)

    for e in extra_parts:
        if e not in out:
            out.append(e)

    # Stable order, dedupe
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _parse_allow_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[\n,\r]+", str(raw))
    return [p.strip() for p in parts if p.strip()]


def _http_json(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            txt = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(txt)
            except json.JSONDecodeError:
                return resp.status, txt
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(txt)
        except json.JSONDecodeError:
            return e.code, txt


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Supabase Auth site URL and redirect allow list")
    parser.add_argument("--dry-run", action="store_true", help="Print planned PATCH body and exit")
    parser.add_argument(
        "--require-token",
        action="store_true",
        help="Exit 1 if no management token (default: exit 0 and skip)",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Less console output")
    args = parser.parse_args()
    _load_dotenv()

    def log(msg: str) -> None:
        if not args.quiet:
            print(msg)

    token = _get_management_token()
    supabase_url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    site_url = _canonical_site_url()
    defaults = _default_redirect_urls()

    if not token:
        if args.require_token:
            print("No Supabase management token. Set SUPABASE_ACCESS_TOKEN or run: supabase login", file=sys.stderr)
            return 1
        if args.dry_run:
            patch = {"site_url": site_url, "uri_allow_list": "\n".join(defaults)}
            print(json.dumps(patch, indent=2))
            print(
                "\n// Note: with a PAT, existing Supabase redirect URLs would be merged with the above.",
                file=sys.stderr,
            )
            return 0
        log("No Supabase PAT (SUPABASE_ACCESS_TOKEN, ~/.supabase/access-token, or supabase login) — skipped.")
        return 0

    try:
        ref = _project_ref_from_supabase_url(supabase_url)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    api = f"https://api.supabase.com/v1/projects/{ref}/config/auth"
    status, cur = _http_json("GET", api, token)
    if status != 200 or not isinstance(cur, dict):
        print(f"GET auth config failed: HTTP {status} {cur!r}", file=sys.stderr)
        return 1

    existing = _parse_allow_list(cur.get("uri_allow_list"))
    merged: list[str] = []
    seen: set[str] = set()
    for u in existing + defaults:
        if u not in seen:
            seen.add(u)
            merged.append(u)

    patch: dict = {
        "site_url": site_url,
        "uri_allow_list": "\n".join(merged),
    }

    gid = (os.environ.get("SUPABASE_SYNC_GOOGLE_CLIENT_ID") or "").strip()
    gsec = (os.environ.get("SUPABASE_SYNC_GOOGLE_CLIENT_SECRET") or "").strip()
    if gid and gsec:
        patch["external_google_enabled"] = True
        patch["external_google_client_id"] = gid
        patch["external_google_secret"] = gsec
        log("Including Google OAuth client id/secret from env in PATCH.")
    elif gid or gsec:
        log("Warning: set both SUPABASE_SYNC_GOOGLE_CLIENT_ID and SUPABASE_SYNC_GOOGLE_CLIENT_SECRET to sync Google.")

    if args.dry_run:
        print(json.dumps(patch, indent=2))
        return 0

    st2, res2 = _http_json("PATCH", api, token, patch)
    if st2 not in (200, 204):
        print(f"PATCH auth config failed: HTTP {st2} {res2!r}", file=sys.stderr)
        if st2 == 403:
            print(
                "Token needs Management API permission to update Auth (e.g. auth_config_write). "
                "Create a new PAT at https://supabase.com/dashboard/account/tokens",
                file=sys.stderr,
            )
        return 1

    log(f"Supabase Auth updated (project {ref}): site_url={site_url!r}, {len(merged)} redirect URLs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
