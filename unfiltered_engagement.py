"""Unfiltered search engagement — leaderboard (anonymized) + optional activity pings."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

unfiltered_bp = Blueprint("unfiltered", __name__, url_prefix="/api/unfiltered")

_TABLE_READY = False
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.I,
)


def _ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    from app import _analytics_execute

    _analytics_execute(
        """
        CREATE TABLE IF NOT EXISTS unfiltered_leaderboard (
          participant_key TEXT PRIMARY KEY,
          display_label TEXT NOT NULL,
          score REAL NOT NULL DEFAULT 0,
          query_count INTEGER NOT NULL DEFAULT 0,
          depth_units REAL NOT NULL DEFAULT 0,
          receipt_events INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT DEFAULT (datetime('now'))
        )
        """,
        [],
    )
    try:
        _analytics_execute(
            "CREATE INDEX IF NOT EXISTS idx_unfiltered_lb_score ON unfiltered_leaderboard(score DESC)",
            [],
        )
    except Exception:
        pass
    _TABLE_READY = True


def _participant_key(participant_id: str) -> str:
    secret = (os.environ.get("SECRET_KEY") or "abbiey-unfiltered").encode()
    return hashlib.sha256(secret + b":" + participant_id.encode("utf-8")).hexdigest()


def _display_label(participant_id: str) -> str:
    h = hashlib.sha256(participant_id.encode("utf-8")).hexdigest()[:5]
    return f"anon-{h}"


@unfiltered_bp.route("/leaderboard", methods=["GET"])
def leaderboard():
    """Top 50 anonymized rows by unfiltered score."""
    try:
        _ensure_table()
        from app import _analytics_execute

        rows = _analytics_execute(
            """
            SELECT display_label, score, query_count, depth_units, receipt_events, updated_at
            FROM unfiltered_leaderboard
            ORDER BY score DESC
            LIMIT 50
            """,
            [],
        )
        out = []
        for i, r in enumerate(rows or [], start=1):
            out.append(
                {
                    "rank": i,
                    "label": (r.get("display_label") or "")[:32],
                    "score": float(r.get("score") or 0),
                    "queries": int(r.get("query_count") or 0),
                    "depth_units": float(r.get("depth_units") or 0),
                    "receipts": int(r.get("receipt_events") or 0),
                }
            )
        return jsonify({"ok": True, "entries": out})
    except Exception:
        logger.exception("unfiltered_leaderboard_failed")
        return jsonify({"ok": False, "entries": []}), 200


@unfiltered_bp.route("/activity", methods=["POST"])
def activity():
    """Increment anonymized score for an unfiltered session (client-generated UUID)."""
    if not request.is_json:
        return jsonify({"ok": False, "error": "json_required"}), 400
    data = request.get_json(silent=True) or {}
    pid = (data.get("participant_id") or "").strip()
    if not _UUID_RE.match(pid):
        return jsonify({"ok": False, "error": "invalid_participant_id"}), 400
    try:
        depth = float(data.get("depth") or 0)
    except (TypeError, ValueError):
        depth = 0.0
    try:
        receipts = int(data.get("receipts") or 0)
    except (TypeError, ValueError):
        receipts = 0
    depth = max(0.0, min(depth, 50.0))
    receipts = max(0, min(receipts, 500))
    score_delta = 1.0 + depth * 0.35 + receipts * 1.5
    now = datetime.now(timezone.utc).isoformat()
    pkey = _participant_key(pid)
    label = _display_label(pid)
    try:
        _ensure_table()
        from app import _analytics_execute

        _analytics_execute(
            """
            INSERT INTO unfiltered_leaderboard
              (participant_key, display_label, score, query_count, depth_units, receipt_events, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(participant_key) DO UPDATE SET
              score = unfiltered_leaderboard.score + excluded.score,
              query_count = unfiltered_leaderboard.query_count + excluded.query_count,
              depth_units = unfiltered_leaderboard.depth_units + excluded.depth_units,
              receipt_events = unfiltered_leaderboard.receipt_events + excluded.receipt_events,
              display_label = excluded.display_label,
              updated_at = excluded.updated_at
            """,
            [pkey, label, score_delta, 1, depth, receipts, now],
        )
        return jsonify({"ok": True})
    except Exception:
        logger.exception("unfiltered_activity_failed")
        return jsonify({"ok": False}), 500


def register_unfiltered_limits(limiter) -> None:
    from flask import current_app

    for ep in ("unfiltered.leaderboard", "unfiltered.activity"):
        fn = current_app.view_functions.get(ep)
        if fn:
            current_app.view_functions[ep] = limiter.limit("120/minute")(fn)
