#!/usr/bin/env python3
"""
Attach production domains to the Vercel project (apex + www).

www -> apex redirect is enforced in vercel.json (edge redirect before the function).

Requires: VERCEL_TOKEN (or token in the Vercel CLI auth.json on Windows).

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

DEFAULT_PROJECT_ID = "prj_meBOJCYxNefYepBikq5fHJFP4tS7"
DEFAULT_TEAM_ID = "team_YeguIG4NHm4Kp0Jf5AbOwgFN"
LEGACY_PROJECT_IDS = ("prj_hGdLqDsNtQK2A57hWyZNxdZKMi3b",)

DOMAINS = ("abbieysearch.com", "www.abbieysearch.com")


def _auth_paths() -> tuple[Path, ...]:
    candidates = [
        Path(os.environ.get("APPDATA", "")) / "xdg.data" / "com.vercel.cli" / "auth.json",
        Path(os.environ.get("APPDATA", "")) / "com.vercel.cli" / "auth.json",
        Path(os.environ.get("APPDATA", "")) / "com.vercel.cli" / "Data" / "auth.json",
        Path(os.environ.get("LOCALAPPDATA", "")) / "com.vercel.cli" / "Data" / "auth.json",
        Path.home() / ".vercel" / "auth.json",
    ]
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path)
        if key and key not in seen:
            seen.add(key)
            unique.append(path)
    return tuple(unique)


def _token() -> str:
    t = (os.environ.get("VERCEL_TOKEN") or "").strip()
    if t:
        return t
    for auth_path in _auth_paths():
        if auth_path.is_file():
            try:
                return json.loads(auth_path.read_text(encoding="utf-8")).get("token", "") or ""
            except Exception:
                continue
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


def _project_domains(project_id: str, token: str, path_suffix: str) -> tuple[int, set[str], dict]:
    status, data = _req("GET", f"/v9/projects/{project_id}/domains{path_suffix}", token)
    domains = {d.get("name", "").lower() for d in data.get("domains", [])} if status == 200 else set()
    return status, domains, data


def _detach_domain(project_id: str, domain: str, token: str, path_suffix: str) -> tuple[int, dict]:
    quoted = urllib.parse.quote(domain, safe="")
    return _req("DELETE", f"/v9/projects/{project_id}/domains/{quoted}{path_suffix}", token)


def _attach_domain(project_id: str, domain: str, token: str, path_suffix: str) -> tuple[int, dict]:
    return _req("POST", f"/v9/projects/{project_id}/domains{path_suffix}", token, {"name": domain})


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
    status, existing, data = _project_domains(project_id, token, path_suffix)
    if status != 200:
        print(f"ERROR: list domains failed HTTP {status}: {data}")
        return 1
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

    candidate_project_ids = []
    env_legacy = (os.environ.get("VERCEL_LEGACY_PROJECT_ID") or "").strip()
    if env_legacy and env_legacy != project_id:
        candidate_project_ids.append(env_legacy)
    for legacy_id in LEGACY_PROJECT_IDS:
        if legacy_id != project_id and legacy_id not in candidate_project_ids:
            candidate_project_ids.append(legacy_id)

    for name in missing:
        st, resp = _attach_domain(project_id, name, token, path_suffix)
        if st in (200, 201):
            print(f"OK  attached {name}")
            continue

        msg = resp.get("error", {}).get("message", str(resp))
        if st == 409 and "already in use by one of your projects" in msg.lower():
            migrated = False
            for legacy_id in candidate_project_ids:
                legacy_status, legacy_domains, legacy_data = _project_domains(legacy_id, token, path_suffix)
                if legacy_status != 200:
                    print(f"WARN legacy project {legacy_id} domains lookup failed: HTTP {legacy_status}: {legacy_data}")
                    continue
                if name.lower() not in legacy_domains:
                    continue
                print(f"Migrating {name} from legacy project {legacy_id} -> {project_id}")
                detach_status, detach_resp = _detach_domain(legacy_id, name, token, path_suffix)
                if detach_status not in (200, 204):
                    detach_msg = detach_resp.get("error", {}).get("message", str(detach_resp))
                    print(f"FAIL {name}: HTTP {detach_status} while detaching from {legacy_id}: {detach_msg}")
                    return 1
                retry_status, retry_resp = _attach_domain(project_id, name, token, path_suffix)
                if retry_status in (200, 201):
                    print(f"OK  migrated {name}")
                    migrated = True
                    break
                retry_msg = retry_resp.get("error", {}).get("message", str(retry_resp))
                print(f"FAIL {name}: HTTP {retry_status} while attaching to {project_id}: {retry_msg}")
                return 1
            if migrated:
                continue

        print(f"FAIL {name}: HTTP {st} {msg}")
        return 1

    print("Done. www traffic redirects to apex via vercel.json redirects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
