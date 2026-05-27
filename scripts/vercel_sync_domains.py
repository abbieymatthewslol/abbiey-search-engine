#!/usr/bin/env python3
"""
Attach production domains to the Vercel project (apex + www).

www -> apex redirect is enforced in vercel.json (edge redirect before the function).

Requires: VERCEL_TOKEN (or token in %APPDATA%\\com.vercel.cli\\Data\\auth.json on Windows).

Usage:
  python scripts/vercel_sync_domains.py           # dry-run: list + plan
  python scripts/vercel_sync_domains.py --apply # POST missing domains
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_PROJECT_ID = "prj_XMC9ngigTMtG8V6wL8kNMary3S1Q"
DEFAULT_TEAM_ID = "team_YeguIG4NHm4Kp0Jf5AbOwgFN"

DOMAINS = ("abbieysearch.com", "www.abbieysearch.com")


def _token() -> str:
    t = (os.environ.get("VERCEL_TOKEN") or "").strip()
    if t:
        return t
    auth_path = Path(os.environ.get("APPDATA", "")) / "com.vercel.cli" / "Data" / "auth.json"
    if auth_path.is_file():
        try:
            return json.loads(auth_path.read_text(encoding="utf-8")).get("token", "") or ""
        except Exception:
            return ""
    return ""


def _req(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"https://api.vercel.com{path}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": {"message": raw.decode("utf-8", "replace")}}


def main() -> int:
    apply_mode = "--apply" in sys.argv
    token = _token()
    project_id = (os.environ.get("VERCEL_PROJECT_ID") or DEFAULT_PROJECT_ID).strip()
    team_id = (
        os.environ.get("VERCEL_TEAM_ID") or os.environ.get("VERCEL_ORG_ID") or DEFAULT_TEAM_ID
    ).strip()
    q = urllib.parse.urlencode({"teamId": team_id}) if team_id else ""

    if not token:
        print("ERROR: VERCEL_TOKEN not set and no Vercel CLI auth.json found.")
        return 1

    path_suffix = f"?{q}" if q else ""
    status, data = _req(
        "GET",
        f"/v9/projects/{project_id}/domains{path_suffix}",
        token,
    )
    if status != 200:
        print(f"ERROR: list domains failed HTTP {status}: {data}")
        return 1
    existing = {d.get("name", "").lower() for d in data.get("domains", [])}
    print(f"Project {project_id} - domains on Vercel: {sorted(existing) or '(none)'}")

    missing = [d for d in DOMAINS if d.lower() not in existing]
    if not missing:
        print("All required domains already attached.")
        print("DNS: ensure apex A/ALIAS to Vercel; www CNAME to cname.vercel-dns.com if prompted.")
        return 0

    print(f"Missing: {missing}")
    if not apply_mode:
        print("Dry run. Re-run with --apply to attach.")
        print("After attach, complete DNS at your registrar per Vercel project -> Domains UI.")
        return 0

    for name in missing:
        st, resp = _req(
            "POST",
            f"/v9/projects/{project_id}/domains{path_suffix}",
            token,
            {"name": name},
        )
        if st in (200, 201):
            print(f"OK  attached {name}")
        else:
            msg = resp.get("error", {}).get("message", str(resp))
            print(f"FAIL {name}: HTTP {st} {msg}")
            return 1

    print("Done. www traffic redirects to apex via vercel.json redirects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
