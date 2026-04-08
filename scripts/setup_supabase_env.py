#!/usr/bin/env python3
"""
One-step local Supabase setup for abbiey.search.

Writes Transaction pooler URI (port 6543, user postgres.<project_ref>) to .env,
removes broken pooler lines, drops DATABASE_URL so SUPABASE_DB_URL is the only DB key,
then copies .env → .env.local (identical; app loads .env only).

Run from repo root:
  python scripts/setup_supabase_env.py
"""
from __future__ import annotations

import getpass
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

_REPO = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO / ".env", override=False)
except ImportError:
    pass

_PROJECT_REF = (os.environ.get("ABBIEY_SUPABASE_PROJECT_REF") or "xwxscvllmghyogddpmii").strip()
_POOLER_HOST = (
    os.environ.get("ABBIEY_SUPABASE_POOLER") or "aws-1-ap-southeast-1.pooler.supabase.com"
).strip()
_POOLER_PORT = "6543"
_DB_KEYS = frozenset({"SUPABASE_DB_URL", "DATABASE_URL"})


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_assignment(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", s)
    if not m:
        return None
    key, val = m.group(1), m.group(2).strip()
    if val.startswith('"') and val.endswith('"'):
        val = val[1:-1]
    elif val.startswith("'") and val.endswith("'"):
        val = val[1:-1]
    return key, val


def _is_invalid_pooler_plain_postgres(value: str) -> bool:
    try:
        canonical = value.strip().replace("postgresql+psycopg2://", "postgresql://", 1)
        p = urlparse(canonical)
        host = (p.hostname or "").lower()
        user = unquote((p.username or "").strip())
        port = p.port or 5432
    except Exception:
        return False
    return "pooler.supabase.com" in host and port == 6543 and user == "postgres"


def _sanitize_env_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        parsed = _parse_assignment(line)
        if not parsed:
            out.append(line)
            continue
        key, val = parsed
        if key not in _DB_KEYS:
            out.append(line)
            continue
        if key == "DATABASE_URL":
            continue
        if key == "SUPABASE_DB_URL" and _is_invalid_pooler_plain_postgres(val):
            continue
        out.append(line)
    return out


def _drop_database_url_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        parsed = _parse_assignment(line)
        if parsed and parsed[0] == "DATABASE_URL":
            continue
        out.append(line)
    return out


def _upsert_line(lines: list[str], key: str, value: str) -> list[str]:
    prefix = key + "="
    out: list[str] = []
    found = False
    for line in lines:
        parsed = _parse_assignment(line)
        if parsed and parsed[0] == key:
            if not found:
                out.append(f"{key}={value}")
                found = True
            continue
        out.append(line)
    if not found:
        out.append(f"{key}={value}")
    return out


def _masked_pooler_url(url: str) -> str:
    try:
        canonical = url.replace("postgresql+psycopg2://", "postgresql://", 1)
        p = urlparse(canonical)
        user = unquote(p.username or "") or "(user)"
        host = p.hostname or "(host)"
        port = p.port or 5432
        return f"postgresql://{user}:***@{host}:{port}{p.path or '/postgres'}"
    except Exception:
        return "postgresql://***:***@***/postgres"


def main() -> int:
    root = _repo_root()
    env_path = root / ".env"
    env_local = root / ".env.local"
    example = root / ".env.example"

    print("abbiey.search — Supabase pooler setup")
    print("-" * 40)
    print("Database password: Supabase → Settings → Database → Database password\n")

    password = getpass.getpass("Paste database password (hidden): ").strip()
    if not password:
        print("Cancelled (empty password).")
        return 1

    user = f"postgres.{_PROJECT_REF}"
    enc = quote(password, safe="")
    url = f"postgresql://{user}:{enc}@{_POOLER_HOST}:{_POOLER_PORT}/postgres"

    if not env_path.exists():
        if example.exists():
            shutil.copy(example, env_path)
            print("Created .env from .env.example")
        else:
            env_path.write_text(
                "SECRET_KEY=change-me\nADMIN_TOKEN=change-me\nPORT=8000\n",
                encoding="utf-8",
            )
            print("Created minimal .env")

    text = env_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    lines = _sanitize_env_lines(lines)
    lines = _drop_database_url_lines(lines)
    lines = _upsert_line(lines, "SUPABASE_DB_URL", url)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    shutil.copyfile(env_path, env_local)
    print("\nWrote SUPABASE_DB_URL to .env and copied .env → .env.local (identical).")
    print("Removed DATABASE_URL entries and invalid pooler URLs (user postgres on :6543).")
    print(f"Verified format (masked): {_masked_pooler_url(url)}")
    print(f"Pooler user: {user}")
    print("\nNext:")
    print("  python scripts/verify_supabase_connection.py")
    print("  python app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
