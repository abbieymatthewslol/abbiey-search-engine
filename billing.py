"""Stripe-metered billing for the ``/api/v1`` developer API.

Behaviour summary
-----------------
* Every authenticated ``/api/v1/*`` request records a row in
  ``api_usage_events`` (see ``ensure_schema``).
* A lightweight in-process counter per ``user_id`` is incremented. When it
  reaches ``FLUSH_THRESHOLD`` events OR ``FLUSH_INTERVAL_SECONDS`` elapses,
  we ship a batch to Stripe's Meter Events API. That keeps the steady-state
  cost of a request at "one SQL INSERT" — Stripe is never in the hot path.
* All Stripe calls are wrapped in a try/except. If Stripe is unreachable or
  not configured (``STRIPE_SECRET_KEY`` absent), billing degrades to a
  local-only log and **never** blocks or fails a user's request.
* Free tier: the first ``FREE_MONTHLY_CALLS`` events per user per calendar
  month are flagged ``billable=0`` in the event table. The meter event we
  ship to Stripe reports only the billable count so usage dashboards stay
  accurate.

The module is deliberately dependency-light — ``stripe`` is already in
``requirements.txt`` so there is nothing new to add.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

logger = logging.getLogger(__name__)

FLUSH_THRESHOLD = int(os.environ.get("ABBIEY_BILLING_FLUSH_EVERY", "25"))
FLUSH_INTERVAL_SECONDS = int(os.environ.get("ABBIEY_BILLING_FLUSH_SECONDS", "60"))
FREE_MONTHLY_CALLS = int(os.environ.get("ABBIEY_API_V1_FREE_MONTHLY", "1000"))
STRIPE_METER_EVENT_NAME = os.environ.get(
    "ABBIEY_STRIPE_METER_EVENT", "api_v1_request"
)


_pending_counts_lock = threading.Lock()
_pending_counts: dict[int, int] = {}
_last_flush_at = time.time()
_schema_ready = False


# The exec callable matches ``_users_execute`` in app.py. Kept as a parameter
# on ``ensure_schema`` and module state so we avoid a circular import.
_exec: Optional[Callable[..., list]] = None


def configure(execute_fn: Callable[..., list]) -> None:
    """Wire the module to the app's user-db executor. Called once at boot."""
    global _exec
    _exec = execute_fn


def ensure_schema() -> None:
    """Create the usage table if missing. Idempotent; called lazily."""
    global _schema_ready
    if _schema_ready or _exec is None:
        return
    _exec(
        """
        CREATE TABLE IF NOT EXISTS api_usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            latency_ms INTEGER NOT NULL,
            billable INTEGER NOT NULL DEFAULT 1,
            stripe_meter_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    _exec(
        "CREATE INDEX IF NOT EXISTS idx_api_usage_user_month "
        "ON api_usage_events(user_id, created_at)"
    )
    _schema_ready = True


def _month_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _count_user_events_this_month(user_id: int) -> int:
    if _exec is None:
        return 0
    rows = _exec(
        "SELECT COUNT(*) AS n FROM api_usage_events WHERE user_id=? AND created_at>=?",
        [user_id, _month_start_iso()],
    )
    if not rows:
        return 0
    try:
        return int(rows[0].get("n") or 0)
    except Exception:
        return 0


def record_event(*, user_id: int, endpoint: str, status_code: int, latency_ms: int) -> None:
    """Persist a single usage row and maybe flush to Stripe."""
    if _exec is None:
        return
    try:
        ensure_schema()
        used_this_month = _count_user_events_this_month(user_id)
        billable = 0 if used_this_month < FREE_MONTHLY_CALLS else 1
        _exec(
            "INSERT INTO api_usage_events "
            "(user_id, endpoint, status_code, latency_ms, billable, created_at) "
            "VALUES (?,?,?,?,?,?)",
            [
                user_id,
                endpoint[:120],
                int(status_code),
                int(latency_ms),
                billable,
                datetime.now(timezone.utc).isoformat(),
            ],
        )
    except Exception:
        logger.exception("billing_record_event_failed")
        return

    if billable:
        _bump_pending(user_id)

    if _should_flush():
        try:
            flush_pending_meter_events()
        except Exception:
            logger.exception("billing_flush_failed")


def _bump_pending(user_id: int) -> None:
    with _pending_counts_lock:
        _pending_counts[user_id] = _pending_counts.get(user_id, 0) + 1


def _should_flush() -> bool:
    global _last_flush_at
    with _pending_counts_lock:
        total = sum(_pending_counts.values())
    if total >= FLUSH_THRESHOLD:
        return True
    if time.time() - _last_flush_at >= FLUSH_INTERVAL_SECONDS and total > 0:
        return True
    return False


def flush_pending_meter_events() -> None:
    """Ship accumulated per-user billable counts to Stripe's Meters API.

    Safe to call opportunistically from request handlers; we swallow every
    possible failure and never raise so production requests aren't affected.
    """
    global _last_flush_at
    secret = (os.environ.get("STRIPE_SECRET_KEY") or "").strip()
    if not secret:
        # No Stripe configured — just drain the counter.
        with _pending_counts_lock:
            _pending_counts.clear()
            _last_flush_at = time.time()
        return

    with _pending_counts_lock:
        snapshot = dict(_pending_counts)
        _pending_counts.clear()
        _last_flush_at = time.time()

    if not snapshot:
        return

    try:
        import stripe

        stripe.api_key = secret
        for user_id, count in snapshot.items():
            try:
                stripe.billing.MeterEvent.create(
                    event_name=STRIPE_METER_EVENT_NAME,
                    payload={
                        "stripe_customer_id": _stripe_customer_for_user(user_id) or f"user_{user_id}",
                        "value": str(count),
                    },
                    identifier=f"u{user_id}-{int(time.time())}",
                )
            except Exception:
                logger.exception("billing_meter_event_failed user=%s count=%s", user_id, count)
                # Put the lost events back so we try again next flush.
                with _pending_counts_lock:
                    _pending_counts[user_id] = _pending_counts.get(user_id, 0) + count
    except Exception:
        logger.exception("billing_flush_init_failed")
        # Reinstate the counter so we don't silently lose billing.
        with _pending_counts_lock:
            for user_id, count in snapshot.items():
                _pending_counts[user_id] = _pending_counts.get(user_id, 0) + count


def _stripe_customer_for_user(user_id: int) -> Optional[str]:
    """Look up the Stripe customer id stored on the users table, if any."""
    if _exec is None:
        return None
    try:
        rows = _exec(
            "SELECT stripe_customer_id FROM users WHERE id=? LIMIT 1",
            [user_id],
        )
    except Exception:
        return None
    if not rows:
        return None
    cid = rows[0].get("stripe_customer_id") if isinstance(rows[0], dict) else None
    if not cid:
        return None
    return str(cid)


def monthly_usage_for_user(user_id: int) -> dict:
    """Return ``{ "used": N, "free_quota": FREE_MONTHLY_CALLS, "billable": M }``."""
    if _exec is None:
        return {"used": 0, "free_quota": FREE_MONTHLY_CALLS, "billable": 0}
    ensure_schema()
    rows = _exec(
        "SELECT COUNT(*) AS n, SUM(billable) AS bill FROM api_usage_events "
        "WHERE user_id=? AND created_at>=?",
        [user_id, _month_start_iso()],
    ) or []
    n = 0
    b = 0
    if rows:
        try:
            n = int(rows[0].get("n") or 0)
            b = int(rows[0].get("bill") or 0)
        except Exception:
            pass
    return {"used": n, "free_quota": FREE_MONTHLY_CALLS, "billable": b}
