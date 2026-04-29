"""Public developer API — `/api/v1/*`.

Design notes
------------
* Everything here is a thin, stable wrapper around existing internal helpers
  in ``app.py``. We never expose an internal structure directly; each route
  picks a deliberate subset so we can refactor internals without breaking
  paying integrators.
* Auth is Bearer-only. We do not accept session cookies on ``/api/v1`` routes
  — it's a developer surface, not a browser surface. That also lets us turn
  on CORS `*` later if we want, without exposing CSRF-sensitive actions.
* Rate limiting is keyed on ``api_user.id`` so abusing one key doesn't eat
  another customer's quota.
* Usage is recorded per authed request in ``api_usage_events``. A periodic
  flusher (``billing.flush_pending_meter_events``) ships those events to
  Stripe's Meters API in batches. All Stripe calls are best-effort — if
  Stripe is down or not configured, metering degrades gracefully to the
  free tier and we never fail a user's request.
"""

from __future__ import annotations

import logging
import os
import time

from flask import Blueprint, current_app, jsonify, request

from retrieval.rank_params import normalize_rank_mode

logger = logging.getLogger(__name__)

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

# Default free tier: 1,000 calls per month per key. Above that, metered
# billing kicks in at the rate documented in docs/API.md.
FREE_MONTHLY_CALLS = int(os.environ.get("ABBIEY_API_V1_FREE_MONTHLY", "1000"))
METERED_CALLS_PER_MINUTE = os.environ.get("ABBIEY_API_V1_RATE", "120/minute")


def _auth_or_401():
    """Bearer-only auth. Returns (user_id, None) on success, (None, resp) on fail."""
    auth = (request.headers.get("Authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return None, (
            jsonify(
                {
                    "error": "unauthorized",
                    "message": "Send an API key as 'Authorization: Bearer <key>'.",
                    "docs": "/docs/api",
                }
            ),
            401,
        )
    token = auth[7:].strip()
    from app import _user_id_from_api_key  # local import avoids circular

    uid = _user_id_from_api_key(token) if token else None
    if uid is None:
        return None, (
            jsonify(
                {
                    "error": "invalid_api_key",
                    "message": "API key missing, malformed, or revoked.",
                    "docs": "/docs/api",
                }
            ),
            401,
        )
    return uid, None


def _record_usage(user_id: int, endpoint: str, status_code: int, latency_ms: int) -> None:
    """Persist a usage row and enqueue a Stripe meter event (best effort)."""
    try:
        import billing

        billing.record_event(user_id=user_id, endpoint=endpoint, status_code=status_code, latency_ms=latency_ms)
    except Exception:  # pragma: no cover - billing is best-effort
        logger.exception("api_v1_usage_record_failed")


def _rate_limit_key() -> str:
    """Per-key rate limiting: authenticated calls share the key, not the IP."""
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return "api_v1_key:" + auth[7:].strip()[:32]
    from flask_limiter.util import get_remote_address

    return get_remote_address()


def _register_limits(limiter) -> None:
    """Attach flask-limiter limits to the blueprint endpoints.

    Called from ``app.py`` at import time after ``limiter`` is configured.
    We do it here (not via decorator on each view) so we can key on the
    API key instead of the IP.
    """
    for view in ("search", "bots_list", "bots_query", "reverse_image"):
        ep = f"api_v1.{view}"
        limiter.limit(METERED_CALLS_PER_MINUTE, key_func=_rate_limit_key)(
            current_app.view_functions[ep]
        )


# ---------------------------------------------------------------------------
# GET /api/v1/health — unauth'd, shows overall status
# ---------------------------------------------------------------------------

@api_v1.route("/health", methods=["GET"])
def health():
    from app import _build_health_payload

    payload = _build_health_payload(include_sensitive=False)
    payload["api_version"] = "1"
    payload["data_region"] = os.environ.get("ABBIEY_DATA_REGION", "sg")
    return jsonify(payload)


# ---------------------------------------------------------------------------
# GET /api/v1/search
# ---------------------------------------------------------------------------

_ALLOWED_TYPES = {"text", "images", "news", "videos", "code", "onion"}
_TIME_FILTERS = {"", "d", "w", "m", "y"}
_MAX_PAGE = 20


@api_v1.route("/search", methods=["GET"])
def search():
    t0 = time.time()
    uid, err = _auth_or_401()
    if err:
        return err

    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "missing_query", "message": "Parameter ?q= is required."}), 400
    if len(query) > int(os.environ.get("ABBIEY_MAX_QUERY_LENGTH", "8000")):
        return jsonify({"error": "query_too_long"}), 400

    search_type = (request.args.get("type") or "text").strip().lower()
    if search_type not in _ALLOWED_TYPES:
        return jsonify(
            {
                "error": "unsupported_type",
                "message": f"type must be one of {sorted(_ALLOWED_TYPES)}",
            }
        ), 400

    page = max(1, min(int(request.args.get("page", "1") or "1"), _MAX_PAGE))
    region = (request.args.get("region") or "").strip() or None
    lang = (request.args.get("lang") or "").strip() or None
    time_filter = (request.args.get("df") or "").strip()
    if time_filter not in _TIME_FILTERS:
        time_filter = ""
    rank_mode = normalize_rank_mode(request.args.get("rank_mode"))

    try:
        from app import _fetch_results

        results = _fetch_results(
            query=query,
            page=page,
            search_type=search_type,
            region=region,
            lang=lang,
            time_filter=time_filter,
            rank_mode=rank_mode,
        )
    except Exception:
        logger.exception("api_v1_search_failed q=%s type=%s", query[:120], search_type)
        _record_usage(uid, "/api/v1/search", 500, int((time.time() - t0) * 1000))
        return jsonify({"error": "search_failed"}), 500

    latency_ms = int((time.time() - t0) * 1000)
    _record_usage(uid, "/api/v1/search", 200, latency_ms)

    return jsonify(
        {
            "query": query,
            "type": search_type,
            "page": page,
            "region": region,
            "lang": lang,
            "time_filter": time_filter or None,
            "has_more": bool(results.get("has_more")),
            "count": len(results.get("results") or []),
            "results": results.get("results") or [],
            "notice": results.get("notice"),
            "latency_ms": latency_ms,
        }
    )


# ---------------------------------------------------------------------------
# GET /api/v1/bots                — list the caller's crawl bots
# POST /api/v1/bots/<id>/query    — keyword search inside a bot's corpus
# ---------------------------------------------------------------------------

@api_v1.route("/bots", methods=["GET"])
def bots_list():
    uid, err = _auth_or_401()
    if err:
        return err
    from app import _users_execute
    from search_bots import parse_json_list

    try:
        rows = _users_execute(
            "SELECT id, name, allow_hosts, seed_urls, max_depth, max_pages, last_crawled_at, last_crawl_status, created_at "
            "FROM user_search_bots WHERE user_id=? ORDER BY id DESC",
            [uid],
        )
    except Exception:
        logger.exception("api_v1_bots_list_failed")
        return jsonify({"error": "bots_list_failed"}), 503
    bots = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "allow_hosts": parse_json_list(r.get("allow_hosts"), max_items=20, max_len_each=120),
            "seed_urls": parse_json_list(r.get("seed_urls"), max_items=20, max_len_each=2000),
            "max_depth": r.get("max_depth"),
            "max_pages": r.get("max_pages"),
            "last_crawled_at": r.get("last_crawled_at"),
            "last_crawl_status": r.get("last_crawl_status"),
        }
        for r in rows or []
    ]
    _record_usage(uid, "/api/v1/bots", 200, 0)
    return jsonify({"bots": bots})


@api_v1.route("/bots/<int:bot_id>/query", methods=["POST"])
def bots_query(bot_id: int):
    t0 = time.time()
    uid, err = _auth_or_401()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    q = (data.get("q") or "").strip()[:400]
    limit = min(int(data.get("limit", 25) or 25), 100)

    from app import _mybot_hits_for_cache, _mybot_owned

    if not _mybot_owned(bot_id, uid):
        return jsonify({"error": "not_found"}), 404
    try:
        hits = _mybot_hits_for_cache(uid, bot_id, q, cap=limit)
    except Exception:
        logger.exception("api_v1_bots_query_failed bot=%s", bot_id)
        _record_usage(uid, "/api/v1/bots/query", 500, int((time.time() - t0) * 1000))
        return jsonify({"error": "query_failed"}), 500

    _record_usage(uid, "/api/v1/bots/query", 200, int((time.time() - t0) * 1000))
    return jsonify({"bot_id": bot_id, "q": q, "count": len(hits), "results": hits})


# ---------------------------------------------------------------------------
# POST /api/v1/reverse-image — multipart image or { "image_url": "…" }
# ---------------------------------------------------------------------------

@api_v1.route("/reverse-image", methods=["POST"])
def reverse_image():
    t0 = time.time()
    uid, err = _auth_or_401()
    if err:
        return err

    # Delegate to the existing session-backed handler to keep the logic in
    # one place. We just translate "no session" + bearer into a synthetic
    # authenticated call.
    from app import api_reverse_image

    resp = api_reverse_image()
    # api_reverse_image returns either a jsonify or a (body, status) tuple.
    status = 200
    body = resp
    if isinstance(resp, tuple):
        body, status = resp[0], resp[1]
    _record_usage(uid, "/api/v1/reverse-image", status, int((time.time() - t0) * 1000))
    return body, status
