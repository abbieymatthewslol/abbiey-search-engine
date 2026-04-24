"""One-shot: Vercel includeFiles + env drift.

Run from repo root:
  python scripts/verify_deployment_config.py
  python scripts/verify_deployment_config.py --strict   # env warnings fail the run

Exits 1 if Vercel or env *errors*; with --strict, env warnings also exit 1.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from verify_vercel_include_files import verify as vercel_verify  # noqa: E402
from verify_env_drift import verify as env_verify  # noqa: E402


def main() -> int:
    strict = "--strict" in sys.argv
    verr, vwarn = vercel_verify()
    eerr, ewarn, ecode = env_verify(strict=strict)

    print("--- Vercel includeFiles ---")
    if verr:
        print("Issues:")
        for x in verr:
            print(f"  - {x}")
    else:
        print("  (none)")

    print("--- Environment ---")
    if eerr:
        print("Issues:")
        for x in eerr:
            print(f"  - {x}")
    else:
        print("  (no format/secret errors)")

    if ewarn:
        print("Warnings (drift):")
        for x in ewarn:
            print(f"  - {x}")

    print("---")
    if verr or eerr:
        return 1
    return ecode


if __name__ == "__main__":
    raise SystemExit(main())
