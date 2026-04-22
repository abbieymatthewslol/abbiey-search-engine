"""Digital-pet blueprint.

Extracted from `app.py` to keep the monolith small. Routes:

- `GET  /pet`              – signed-in pet dashboard
- `GET  /pet/leaderboard`  – public top-100 leaderboard
- `GET  /api/pet/me`       – JSON pet snapshot for the current user
- `POST /api/pet/species`  – change chosen species
- `POST /api/pet/activity` – server-enforced XP awards for client actions

Per-view rate limits are applied by `app.py` when the blueprint is registered
(flask-limiter doesn't persist the original inline `@limiter.limit(...)`
decorators once the view is defined outside the decorated app).

Helpers like `_require_login`, `_api_auth_user`, `_users_execute`,
`_pet_*` and `_session_user_id_int` still live in `app.py`. We import them
lazily at call time to sidestep a circular-import between `app` and
`blueprints.*`.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

import digital_pet as _digital_pet

pet_bp = Blueprint("pet", __name__)


def _app():
    """Return the `app` module, imported lazily to avoid circular import."""
    import app as _app_mod
    return _app_mod


@pet_bp.route("/pet", endpoint="pet_home")
def pet_home():
    a = _app()
    redir = a._require_login()
    if redir:
        return redir
    uid = a._session_user_id_int(session.get("user_id"))
    if not uid:
        return redirect(url_for("login", next="/pet"))
    snap = a._pet_snapshot_for_user(uid)
    return render_template("pet.html", pet=snap, species_list=list(_digital_pet.PET_SPECIES))


@pet_bp.route("/pet/leaderboard", endpoint="pet_leaderboard")
def pet_leaderboard():
    a = _app()
    rows = []
    try:
        rows = a._users_execute(
            "SELECT u.username, u.display_name, p.species, p.xp_total, p.last_activity_at, "
            "u.id AS user_id, u.created_at "
            "FROM user_pet p INNER JOIN users u ON u.id = p.user_id "
            "WHERE p.xp_total > 0 "
            "ORDER BY p.xp_total DESC, p.last_activity_at DESC, u.created_at ASC "
            "LIMIT 100",
            [],
        )
    except Exception:
        a.logger.exception("pet_leaderboard_failed")
    ranked = []
    for i, r in enumerate(rows or [], start=1):
        xp = int(r.get("xp_total") or 0)
        uid = int(r["user_id"])
        st = _digital_pet.stage_from_xp(xp)
        ranked.append(
            {
                "rank": i,
                "username": r.get("username") or "",
                "display_name": r.get("display_name") or "",
                "species": (r.get("species") or "hummingbird").lower(),
                "xp_total": xp,
                "level": _digital_pet.level_from_xp(xp),
                "stage": st,
                "is_you": uid == a._session_user_id_int(session.get("user_id")),
            }
        )
    return render_template("pet_leaderboard.html", leaderboard=ranked)


@pet_bp.route("/api/pet/me", methods=["GET"], endpoint="api_pet_me")
def api_pet_me():
    a = _app()
    uid, bearer_err = a._api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    return jsonify({"pet": a._pet_snapshot_for_user(uid)})


@pet_bp.route("/api/pet/species", methods=["POST"], endpoint="api_pet_species")
def api_pet_species():
    a = _app()
    uid, bearer_err = a._api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json(silent=True) or {}
    sp = (data.get("species") or "").strip().lower()
    if sp not in _digital_pet.PET_SPECIES:
        return jsonify({"error": "Invalid species"}), 400
    try:
        a._pet_ensure_row(uid)
        a._users_execute("UPDATE user_pet SET species=? WHERE user_id=?", [sp, uid])
    except Exception:
        a.logger.exception("api_pet_species_failed")
        return jsonify({"error": "Could not save"}), 503
    return jsonify({"ok": True, "pet": a._pet_snapshot_for_user(uid)})


@pet_bp.route("/api/pet/activity", methods=["POST"], endpoint="api_pet_activity")
def api_pet_activity():
    """Client-reported actions (e.g. share). Server enforces cooldowns and caps."""
    a = _app()
    uid, bearer_err = a._api_auth_user()
    if bearer_err:
        return bearer_err
    if not uid:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip().lower()
    if action != "share":
        return jsonify({"error": "Unsupported action"}), 400
    out = a._pet_try_award(uid, "share")
    out["pet"] = a._pet_snapshot_for_user(uid)
    return jsonify(out)


# Per-view rate limits preserved from the original inline routes.
# `app.py` re-applies them (flask-limiter tracks limits by function qualname,
# so decorating the same function objects before `register_blueprint` works).
RATE_LIMITS = {
    api_pet_species: "30/minute",
    api_pet_activity: "120/minute",
}
