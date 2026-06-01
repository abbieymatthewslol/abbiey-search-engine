#!/usr/bin/env python3
"""
One-shot production release: env sync -> domains -> deploy -> HTTP probes.

Prerequisites (machine or CI):
  - Repo-root .env with secrets (never committed)
  - VERCEL_TOKEN with access to the production project
  - Optional: ADMIN_TOKEN in .env for /admin/api/health?token= probe

Does not print secrets. Exits non-zero on first hard failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_JSON = REPO_ROOT / ".vercel" / "project.json"
EXPECTED_PROJECT = {
    "projectId": "prj_meBOJCYxNefYepBikq5fHJFP4tS7",
    "orgId": "team_YeguIG4NHm4Kp0Jf5AbOwgFN",
    "projectName": "search-engine-2-recovery",
}


def _load_dotenv_keys() -> None:
    for name in (".env", ".env.local"):
        p = REPO_ROOT / name
        if not p.is_file():
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)


def _ensure_project_link() -> None:
    PROJECT_JSON.parent.mkdir(parents=True, exist_ok=True)
    if PROJECT_JSON.is_file():
        try:
            cur = json.loads(PROJECT_JSON.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
        if cur.get("projectId") == EXPECTED_PROJECT["projectId"] and cur.get("orgId") == EXPECTED_PROJECT["orgId"]:
            return
    PROJECT_JSON.write_text(json.dumps(EXPECTED_PROJECT, indent=2) + "\n", encoding="utf-8")


def _run(py_args: list[str]) -> None:
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / py_args[0])] + py_args[1:],
        cwd=str(REPO_ROOT),
    )
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def _http_get(url: str, timeout: float = 25.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "abbiey-full-vercel-release"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, (resp.read(8000) or b"").decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, (e.read(4000) or b"").decode("utf-8", "replace")


def main() -> int:
    os.chdir(REPO_ROOT)
    _load_dotenv_keys()
    skip_deploy = "--skip-deploy" in sys.argv
    skip_domains = "--skip-domains" in sys.argv

    _ensure_project_link()

    _run(["restore_vercel_env.py", "--apply", "--all-targets"])
    if not skip_domains:
        _run(["vercel_sync_domains.py", "--apply"])

    if not skip_deploy:
        token = (os.environ.get("VERCEL_TOKEN") or "").strip()
        if not token:
            print("ERROR: VERCEL_TOKEN required for deploy step (or use --skip-deploy).")
            return 1
        deploy = subprocess.run(
            ["npx", "--yes", "vercel@54.6.1", "deploy", "--prod", "--yes", "--token", token],
            cwd=str(REPO_ROOT),
        )
        if deploy.returncode != 0:
            return deploy.returncode

    # Probes
    pub_url = "https://abbieysearch.com/health"
    code, body = _http_get(pub_url)
    if code != 200:
        print(f"ERROR: {pub_url} returned HTTP {code}")
        return 1
    if '"status"' not in body and "ok" not in body.lower():
        print(f"WARN: unexpected body from {pub_url}")

    admin_tok = (os.environ.get("ADMIN_TOKEN") or "").strip()
    if admin_tok:
        au = f"https://abbieysearch.com/admin/api/health?token={urllib.parse.quote(admin_tok)}"
        ac, ab = _http_get(au)
        if ac != 200:
            print(f"ERROR: admin health returned HTTP {ac}")
            return 1
        if "analytics_db" not in ab:
            print("WARN: admin health JSON missing analytics_db")

    print("OK  release pipeline finished (public /health = 200).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
