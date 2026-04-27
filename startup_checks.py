"""Hard env-var assertions run at app boot.

Why
---
Historically, the #1 production incident has been "feature X silently 422'd
because env var Y wasn't set on Vercel". A ``SITE_URL`` typo in the Vercel
dashboard turned off reverse-image upload; a missing
``SUPABASE_SERVICE_ROLE_KEY`` broke Supabase Storage; and so on.

The fix is boring and effective: when we detect we're running in a
production-like environment (`VERCEL=1`, `FLASK_ENV=production`, or
``ENV=production``), we assert that a closed list of env vars is present
**before** the first request is served, and we fail loud. Any deploy that
skipped an env var dies on boot instead of limping silently.

This module intentionally has no Flask dependency so it's cheap to import
during cold start. It is called from ``app.py`` once after the app object
is built and before any routes are registered.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Requirement:
    name: str
    reason: str
    # If set, the requirement is also skipped when *any* of these are truthy
    # (placeholder for feature-gated env checks).
    skip_if_any_set: tuple[str, ...] = ()


# Core envs required in every production deploy.
_REQUIRED: tuple[Requirement, ...] = (
    Requirement("SECRET_KEY", "Flask session signing key"),
    Requirement("ADMIN_TOKEN", "Protects /admin/* and the bot-crawl worker"),
    Requirement("SITE_URL", "Used by OAuth callbacks and canonical OG / share URLs"),
    Requirement("SUPABASE_URL", "Primary database for users / bookmarks / API keys"),
    Requirement("SUPABASE_ANON_KEY", "Browser-safe Supabase key for auth forms"),
    Requirement(
        "SUPABASE_SERVICE_ROLE_KEY",
        "Reverse-image upload bucket + admin tooling",
    ),
    Requirement(
        "SUPABASE_DB_URL",
        "Postgres pooler URL (port 6543). Required for persistent data.",
    ),
)

# Recommended envs — warn if missing, but do not fail boot.
_RECOMMENDED: tuple[Requirement, ...] = (
    Requirement(
        "COMMUNITY_DISCORD_URL",
        "Shown on /community + footer. Add a community link to close the 'no community' finding.",
    ),
    Requirement(
        "COMMUNITY_GITHUB_URL",
        "Shown on /community + footer.",
    ),
    Requirement(
        "COMMUNITY_MATRIX_URL",
        "Shown on /community + footer.",
    ),
)

# Reserved for feature-gated requirements (e.g. optional integrations).
_CONDITIONAL: tuple[tuple[Requirement, str], ...] = ()

def is_production() -> bool:
    """True if we're booting in a prod-like serverless environment."""
    env = (os.environ.get("FLASK_ENV") or os.environ.get("ENV") or "").strip().lower()
    if env in {"production", "prod"}:
        return True
    if os.environ.get("VERCEL") == "1":
        return True
    if os.environ.get("RAILWAY_ENVIRONMENT_NAME") in {"production", "prod"}:
        return True
    return False


def _missing(reqs: Iterable[Requirement]) -> list[Requirement]:
    out: list[Requirement] = []
    for r in reqs:
        if any((os.environ.get(k) or "").strip() for k in r.skip_if_any_set):
            continue
        if not (os.environ.get(r.name) or "").strip():
            out.append(r)
    return out


def assert_production_env(*, strict: bool | None = None) -> None:
    """Fail boot if any required env is missing in production.

    ``strict=True`` overrides the environment detection and always enforces;
    ``strict=False`` warns only. The default (``None``) detects prod
    automatically. Respects the ``ABBIEY_SKIP_STARTUP_CHECKS=1`` escape hatch
    for self-hosters who know what they're doing (documented in SELF-HOSTING.md).
    """
    if os.environ.get("ABBIEY_SKIP_STARTUP_CHECKS", "").strip().lower() in {"1", "true", "yes"}:
        logger.warning("startup_checks: ABBIEY_SKIP_STARTUP_CHECKS set - skipping env validation")
        return
    if os.environ.get("RUNNING_PYTEST") == "1":
        return

    enforce = strict if strict is not None else is_production()
    missing = _missing(_REQUIRED)
    missing.extend(
        _missing(
            req
            for req, gate_env in _CONDITIONAL
            if (os.environ.get(gate_env) or "").strip()
        )
    )

    if not missing:
        logger.info("startup_checks: all %d required envs present", len(_REQUIRED))
    else:
        banner = "\n".join(f"  - {r.name}: {r.reason}" for r in missing)
        msg = (
            f"\n==== abbiey.search startup_checks ====\n"
            f"Missing {len(missing)} required env var(s) for production:\n{banner}\n"
            f"Set these in your deployment platform (Vercel dashboard, fly secrets, docker -e, ...)\n"
            f"and redeploy. To silence temporarily (NOT recommended) set "
            f"ABBIEY_SKIP_STARTUP_CHECKS=1.\n"
            f"======================================\n"
        )
        if enforce:
            sys.stderr.write(msg)
            raise SystemExit(78)  # EX_CONFIG per /usr/include/sysexits.h
        logger.warning(msg)

    # Recommended (warn only, never fatal)
    missing_recommended = _missing(_RECOMMENDED)
    if missing_recommended:
        banner = "\n".join(f"  - {r.name}: {r.reason}" for r in missing_recommended)
        msg = (
            f"\n==== abbiey.search startup_checks (recommended) ====\n"
            f"Missing {len(missing_recommended)} recommended env var(s):\n{banner}\n"
            f"These are optional, but filling them improves trust signals.\n"
            f"======================================\n"
        )
        logger.warning(msg)


def summarize_config() -> dict:
    """Return a non-sensitive summary for /admin/api/health reuse."""
    present = [r.name for r in _REQUIRED if (os.environ.get(r.name) or "").strip()]
    missing = [r.name for r in _missing(_REQUIRED)]
    recommended_present = [r.name for r in _RECOMMENDED if (os.environ.get(r.name) or "").strip()]
    recommended_missing = [r.name for r in _missing(_RECOMMENDED)]
    return {
        "required_total": len(_REQUIRED),
        "required_present": len(present),
        "required_missing": missing,
        "recommended_total": len(_RECOMMENDED),
        "recommended_present": len(recommended_present),
        "recommended_missing": recommended_missing,
        "is_production": is_production(),
    }
