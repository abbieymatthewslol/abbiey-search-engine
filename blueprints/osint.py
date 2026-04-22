"""OSINT (Open Source Intelligence) API blueprint.

Holds the single `/api/osint/enrich` endpoint extracted from `app.py`. The view
delegates all real work to `osint.service`; this module exists so the route
definition can live outside the 10k-line monolith.

Rate-limiting is applied by `app.py` after the `Limiter` is built, via
`limiter.limit("30/minute")(osint_bp)`.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from osint.service import enrich as _osint_enrich_run
from osint.service import enrich_from_query as _osint_enrich_from_query
from osint.service import is_osint_enabled as _abbiey_osint_enabled

osint_bp = Blueprint("osint", __name__)


@osint_bp.route("/api/osint/enrich", methods=["POST"], endpoint="api_osint_enrich")
def api_enrich():
    """On-demand public OSINT (DNS / RDAP / PTR; optional TLS, dig, whois).

    Not logged as search history.
    """
    if not _abbiey_osint_enabled():
        return (
            jsonify(
                {"ok": False, "error": "disabled", "facts": [], "modules": [], "entity": None}
            ),
            404,
        )
    if not request.is_json:
        return (
            jsonify(
                {"ok": False, "error": "json_required", "facts": [], "modules": [], "entity": None}
            ),
            400,
        )
    data = request.get_json(silent=True) or {}
    q = (data.get("query") or "").strip()
    et = (data.get("entity_type") or "").strip().lower()
    val = (data.get("value") or "").strip()
    if et and val:
        payload = _osint_enrich_run(entity_type=et, value=val)
    elif q:
        payload = _osint_enrich_from_query(q)
    else:
        return (
            jsonify(
                {"ok": False, "error": "missing_body", "facts": [], "modules": [], "entity": None}
            ),
            400,
        )
    status = 200 if payload.get("ok") else 422
    return jsonify(payload), status
