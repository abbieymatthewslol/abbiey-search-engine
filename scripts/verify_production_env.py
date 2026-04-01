#!/usr/bin/env python3
"""
verify_production_env.py — Check production configuration (local .env or CI secrets).

Usage:
  python scripts/verify_production_env.py           # advisory only, exit 0
  python scripts/verify_production_env.py --strict  # exit 1 if core vars missing/weak
  python scripts/verify_production_env.py --ping    # GET /admin/api/health (needs SITE_URL + ADMIN_TOKEN)

In GitHub Actions, pass env from repository secrets (see .github/workflows/production-readiness.yml).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _truthy(val: str | None) -> bool:
    return bool(val and str(val).strip())


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _sk_ok() -> bool:
    sk = (os.environ.get("SECRET_KEY") or "").strip()
    if not sk:
        return False
    low = sk.lower()
    placeholders = (
        "change-me-to-something-random-and-long",
        "change-me-to-something-secret",
    )
    return len(sk) >= 16 and low not in placeholders


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify production-related environment variables")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if SECRET_KEY or ADMIN_TOKEN missing/weak",
    )
    parser.add_argument(
        "--ping",
        action="store_true",
        help="Request live /admin/api/health (needs ADMIN_TOKEN and SITE_URL or CANONICAL_URL)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable summary on stdout",
    )
    args = parser.parse_args()
    _load_dotenv()

    rows: list[tuple[str, str, bool, str]] = []

    def add(name: str, category: str, ok: bool, hint: str) -> None:
        rows.append((name, category, ok, hint))

    add("SECRET_KEY", "core", _sk_ok(), "Long random value; not a placeholder")
    add("ADMIN_TOKEN", "core", _truthy(os.environ.get("ADMIN_TOKEN")), "Protects /admin/*")

    db = _truthy(os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL"))
    add("SUPABASE_DB_URL or DATABASE_URL", "database", db, "Pooler URI on Vercel (port 6543)")

    resend = _truthy(os.environ.get("RESEND_API_KEY"))
    add("RESEND_API_KEY", "email", resend, "Sends signup verification; omit only for dev")
    add("EMAIL_FROM", "email", _truthy(os.environ.get("EMAIL_FROM")), "Must match verified domain in Resend")

    site = _truthy(os.environ.get("SITE_URL") or os.environ.get("CANONICAL_URL"))
    add("SITE_URL or CANONICAL_URL", "urls", site, "Verification links and OG tags")

    core_ok = rows[0][2] and rows[1][2]
    strict_fail = args.strict and not core_ok

    ping_ok: bool | None = None
    ping_detail = ""
    if args.ping:
        base = (os.environ.get("SITE_URL") or os.environ.get("CANONICAL_URL") or "").strip().rstrip("/")
        tok = (os.environ.get("ADMIN_TOKEN") or "").strip()
        if not base or not tok:
            ping_ok = False
            ping_detail = "Set SITE_URL (or CANONICAL_URL) and ADMIN_TOKEN for --ping"
        else:
            q = urllib.parse.urlencode({"token": tok})
            url = f"{base}/admin/api/health?{q}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "verify_production_env/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    ping_ok = False
                    ping_detail = "Response was not JSON (check SITE_URL points to this app)"
                else:
                    if data.get("error"):
                        ping_ok = False
                        ping_detail = f"API error: {data.get('error')!r}"
                    else:
                        ping_ok = data.get("status") in ("ok", "degraded")
                        ping_detail = f"status={data.get('status')!r} storage={data.get('storage')!r}"
            except urllib.error.HTTPError as e:
                ping_ok = False
                try:
                    raw = e.read().decode("utf-8", errors="replace")
                except Exception:
                    raw = ""
                ping_detail = f"HTTP {e.code}"
                try:
                    errj = json.loads(raw)
                    if errj.get("error"):
                        ping_detail = f"HTTP {e.code}: {errj.get('error')}"
                except json.JSONDecodeError:
                    if raw:
                        ping_detail = f"HTTP {e.code} (non-JSON body)"
            except Exception as exc:
                ping_ok = False
                ping_detail = str(exc)[:200]

    if args.json:
        out = {
            "core_ok": core_ok,
            "strict_would_fail": strict_fail,
            "checks": [
                {"name": n, "category": c, "ok": o, "hint": h} for n, c, o, h in rows
            ],
        }
        if args.ping:
            out["ping_ok"] = ping_ok
            out["ping_detail"] = ping_detail
        print(json.dumps(out, indent=2))
    else:
        print("abbiey.search - production environment check\n")
        for name, cat, ok, hint in rows:
            mark = "OK " if ok else "!! "
            print(f"  [{mark}] {name} ({cat})")
            if not ok:
                print(f"         -> {hint}")
        if args.ping:
            print()
            if ping_ok is True:
                print(f"  [OK ] Live health: {ping_detail}")
            else:
                print(f"  [!! ] Live health: {ping_detail}")
        if not args.strict and not args.ping:
            print(
                "Note: advisory mode always exits 0. Use --strict or --ping for failing checks.\n"
            )

    if strict_fail:
        print("Strict mode: fix core variables above (SECRET_KEY, ADMIN_TOKEN).", file=sys.stderr)
        return 1
    if args.ping and ping_ok is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
