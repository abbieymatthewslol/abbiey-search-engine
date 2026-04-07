#!/usr/bin/env python3
"""
One-step local Supabase setup for abbiey.search

You only need your DATABASE password from:
  Supabase → Project Settings → Database → (reset if you forgot)

Run from repo root:
  python scripts/setup_supabase_env.py

Or double-click: setup_supabase.bat (Windows)
"""
from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

# Your project’s Transaction pooler (from Supabase “Connect” → URI → Transaction pooler).
# If you create a new Supabase project, change these three lines to match the dashboard.
_PROJECT_REF = os.environ.get("ABBIEY_SUPABASE_REF", "xwxscvllmghyogddpmii")
_POOLER_HOST = os.environ.get("ABBIEY_SUPABASE_POOLER", "aws-1-ap-southeast-1.pooler.supabase.com")
_POOLER_PORT = "6543"


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _upsert_line(lines: list[str], key: str, value: str) -> list[str]:
    prefix = key + "="
    out: list[str] = []
    found = False
    for line in lines:
        s = line.strip()
        if s.startswith(prefix) or s.startswith(key + " ="):
            if not found:
                out.append(f"{key}={value}")
                found = True
            continue
        if key == "SUPABASE_DB_URL" and (
            s.startswith("DATABASE_URL=") or s.startswith("DATABASE_URL =")
        ):
            continue
        out.append(line)
    if not found:
        out.append(f"{key}={value}")
    return out


def main() -> int:
    root = _repo_root()
    env_path = root / ".env"
    example = root / ".env.example"

    print("abbiey.search — Supabase setup")
    print("-" * 40)
    print("Get your password: Supabase → Settings → Database → Database password")
    print("(Use “Reset database password” if you don’t have it.)\n")

    password = getpass.getpass("Paste database password (hidden): ").strip()
    if not password:
        print("No password entered — cancelled.")
        return 1

    user = f"postgres.{_PROJECT_REF}"
    enc = quote(password, safe="")
    url = f"postgresql://{user}:{enc}@{_POOLER_HOST}:{_POOLER_PORT}/postgres"

    if not env_path.exists():
        if example.exists():
            shutil.copy(example, env_path)
            print(f"Created .env from .env.example")
        else:
            env_path.write_text(
                "SECRET_KEY=change-me\nADMIN_TOKEN=change-me\nPORT=8000\n",
                encoding="utf-8",
            )
            print("Created minimal .env")

    text = env_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    lines = _upsert_line(lines, "SUPABASE_DB_URL", url)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\nDone — saved SUPABASE_DB_URL in .env (password not shown).")
    print("\nNext commands:")
    print("  pip install -r requirements.txt")
    print("  python scripts/verify_supabase_connection.py")
    print("  python app.py")
    print("\nDeploy: set the same SUPABASE_DB_URL in Render / Vercel / etc. (paste from .env).")

    # Best-effort: sync Auth Site URL + redirect allow list (needs supabase login or SUPABASE_ACCESS_TOKEN)
    try:
        r = subprocess.run(
            [sys.executable, str(root / "scripts" / "sync_supabase_auth_config.py")],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=45,
        )
        if r.stdout.strip():
            print(r.stdout.strip())
        if r.returncode != 0 and r.stderr.strip():
            print(r.stderr.strip())
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"(Auth URL sync skipped: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
