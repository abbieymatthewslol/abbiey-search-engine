"""Digital animal (avatar) gamification — constants and pure helpers.

Server-side XP, caps, and DB writes live in app.py. This module stays import-safe
(no Flask) for tests and clarity.
"""

from __future__ import annotations

import math
from typing import Final

PET_SPECIES: Final[tuple[str, ...]] = ("hummingbird", "firefly", "snake", "dolphin")

# action -> base XP (before daily cap trimming)
PET_ACTION_XP: Final[dict[str, int]] = {
    "search": 1,
    "bookmark": 3,
    "share": 5,
}

DAILY_XP_CAP: Final[int] = 200
SEARCH_MAX_PER_HOUR: Final[int] = 40
SHARE_COOLDOWN_SECONDS: Final[int] = 120


def stage_from_xp(xp_total: int) -> int:
    """Visual stage 0–3 (muted → premium)."""
    x = max(0, int(xp_total or 0))
    if x < 30:
        return 0
    if x < 100:
        return 1
    if x < 250:
        return 2
    return 3


def level_from_xp(xp_total: int) -> int:
    """Display level from total XP (soft curve, capped)."""
    x = max(0, int(xp_total or 0))
    if x <= 0:
        return 1
    lv = int(math.sqrt(x / 20.0)) + 1
    return min(99, max(1, lv))


def tier_from_percentile_rank(pct: float) -> str:
    """pct in [0,1], 0 = best. Returns tier key for cosmetics / perks."""
    p = min(1.0, max(0.0, float(pct)))
    if p <= 0.01:
        return "platinum"
    if p <= 0.05:
        return "gold"
    if p <= 0.20:
        return "silver"
    if p <= 0.50:
        return "bronze"
    return "novice"


def bookmark_cap_for_tier(tier: str) -> int:
    """Extra bookmark slots for engaged users (cosmetic-adjacent utility)."""
    if tier in ("platinum", "gold"):
        return 150
    if tier == "silver":
        return 130
    if tier == "bronze":
        return 110
    return 100
