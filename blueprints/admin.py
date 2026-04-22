"""Admin blueprint — analytics dashboard, JSON stats APIs, SSE stream, and AI chat.

Contains the eight `/admin*` routes that used to live in `app.py`:

- `GET  /admin/analytics`           – legacy SQL-rendered HTML analytics page
- `GET  /admin`                     – main dashboard HTML (admin.html)
- `GET  /admin/api/stats`           – dashboard JSON payload
- `GET  /admin/api/query-log`       – paginated search log
- `GET  /admin/api/account-history` – paginated logged-in-user history
- `GET  /admin/api/stream`          – Server-Sent Events stream of live events
- `GET  /admin/api/health`          – health probe with DB + cache stats
- `POST /admin/api/chat`            – internal admin AI assistant

Every route is still gated by `_ADMIN_TOKEN` (reused from `app.py` via the
`_admin_check` helper) — the extraction is structural only.

Helpers like `_analytics_execute`, `_users_execute`, `_active_storage`,
`_build_health_payload`, `_abbiey_bot_fallback`, and `_get_http` continue
to live in `app.py`. We resolve them lazily through the `_app()` shim so
this module can be imported before `app.py` has finished wiring its own
globals (prevents circular-import-at-top).
"""
from __future__ import annotations

import datetime as _dt
import os
import queue

from flask import Blueprint, Response, jsonify, render_template, request

admin_bp = Blueprint("admin", __name__)


def _app():
    """Return the `app` module, imported lazily to avoid circular imports."""
    import app as _app_mod
    return _app_mod


# ---------------------------------------------------------------------------
# HTML dashboards
# ---------------------------------------------------------------------------


@admin_bp.route("/admin/analytics", endpoint="admin_analytics")
def admin_analytics():
    """Admin analytics dashboard — protected by ADMIN_TOKEN query param."""
    a = _app()
    token = request.args.get("token", "")
    if not a._ADMIN_TOKEN or token != a._ADMIN_TOKEN:
        return (
            render_template(
                "error.html",
                code=403,
                title="Forbidden",
                message="Invalid or missing admin token.",
            ),
            403,
        )

    stats: dict = {}
    try:
        rows = a._analytics_execute("SELECT COUNT(*) as cnt FROM search_logs")
        stats["total_all_time"] = rows[0]["cnt"] if rows else 0

        rows = a._analytics_execute(
            "SELECT COUNT(*) as cnt FROM search_logs WHERE created_at >= date('now')"
        )
        stats["total_today"] = rows[0]["cnt"] if rows else 0

        rows = a._analytics_execute(
            "SELECT COUNT(*) as cnt FROM search_logs "
            "WHERE created_at >= datetime('now','-7 days')"
        )
        stats["total_week"] = rows[0]["cnt"] if rows else 0

        raw = a._analytics_execute(
            "SELECT query, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days')"
            "   AND length(query) BETWEEN 2 AND 80"
            " GROUP BY lower(query) ORDER BY cnt DESC LIMIT 20"
        )
        stats["top_queries"] = [(r["query"], r["cnt"]) for r in raw]

        raw = a._analytics_execute(
            "SELECT search_type, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days')"
            " GROUP BY search_type ORDER BY cnt DESC"
        )
        stats["by_type"] = [(r["search_type"], r["cnt"]) for r in raw]

        raw = a._analytics_execute(
            "SELECT hour, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days')"
            " GROUP BY hour ORDER BY hour"
        )
        stats["by_hour"] = [(r["hour"], r["cnt"]) for r in raw]

        raw = a._analytics_execute(
            "SELECT date(created_at) as day, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-30 days')"
            " GROUP BY day ORDER BY day"
        )
        stats["daily"] = [(r["day"], r["cnt"]) for r in raw]

        raw = a._analytics_execute(
            "SELECT region, COUNT(*) as cnt FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days') AND region != ''"
            " GROUP BY region ORDER BY cnt DESC LIMIT 10"
        )
        stats["top_regions"] = [(r["region"], r["cnt"]) for r in raw]

        hour_map = {r[0]: r[1] for r in stats["by_hour"]}
        stats["hours"] = [(h, hour_map.get(h, 0)) for h in range(24)]
        max_hour = max((v for _, v in stats["hours"]), default=1) or 1
        stats["hours_pct"] = [(h, round(v / max_hour * 100)) for h, v in stats["hours"]]

        daily_map = {r[0]: r[1] for r in stats["daily"]}
        today = _dt.date.today()
        stats["daily_chart"] = [
            (
                (today - _dt.timedelta(days=29 - i)).isoformat(),
                daily_map.get((today - _dt.timedelta(days=29 - i)).isoformat(), 0),
            )
            for i in range(30)
        ]
        max_daily = max((v for _, v in stats["daily_chart"]), default=1) or 1
        stats["daily_pct"] = [
            (d, v, round(v / max_daily * 100)) for d, v in stats["daily_chart"]
        ]

    except Exception as exc:
        a.logger.error("Analytics dashboard error: %s", exc)
        stats["error"] = str(exc)

    return render_template("analytics.html", stats=stats)


@admin_bp.route("/admin", endpoint="admin_dashboard")
def admin_dashboard():
    """Main admin dashboard — protected by ADMIN_TOKEN."""
    a = _app()
    token = request.args.get("token", "")
    if not a._ADMIN_TOKEN or token != a._ADMIN_TOKEN:
        return (
            render_template(
                "error.html", code=403, title="Forbidden", message="Admin access only."
            ),
            403,
        )
    return render_template("admin.html", token=token)


# ---------------------------------------------------------------------------
# JSON stats APIs
# ---------------------------------------------------------------------------


@admin_bp.route("/admin/api/stats", endpoint="admin_api_stats")
def admin_api_stats():
    """JSON stats endpoint for the admin dashboard — real data, Turso or SQLite."""
    a = _app()
    err = a._admin_check()
    if err:
        return err
    data: dict = {"storage": a._active_storage()}
    try:
        def _scalar(sql, args=None):
            rows = a._analytics_execute(sql, args or [])
            if rows:
                v = list(rows[0].values())[0]
                return v
            return 0

        data["searches_today"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs WHERE created_at >= date('now')"
        )
        data["searches_week"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs "
            "WHERE created_at >= datetime('now','-7 days')"
        )
        data["searches_total"] = _scalar("SELECT COUNT(*) as c FROM search_logs")
        data["searches_last_hour"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs "
            "WHERE created_at >= datetime('now','-1 hour')"
        )
        data["searches_last_5min"] = _scalar(
            "SELECT COUNT(*) as c FROM search_logs "
            "WHERE created_at >= datetime('now','-5 minutes')"
        )
        data["avg_latency_ms"] = (
            _scalar(
                "SELECT ROUND(AVG(latency_ms)) as c FROM search_logs"
                " WHERE latency_ms > 0 AND created_at >= datetime('now','-7 days')"
            )
            or 0
        )
        data["p95_latency_ms"] = (
            _scalar(
                "SELECT latency_ms as c FROM search_logs WHERE latency_ms > 0"
                " AND created_at >= datetime('now','-7 days')"
                " ORDER BY latency_ms LIMIT 1 OFFSET MAX(0,"
                "(SELECT COUNT(*)*95/100 FROM search_logs WHERE latency_ms > 0"
                " AND created_at >= datetime('now','-7 days'))-1)"
            )
            or 0
        )
        data["errors_today"] = _scalar(
            "SELECT COUNT(*) as c FROM error_logs WHERE created_at >= date('now')"
        )
        data["errors_week"] = _scalar(
            "SELECT COUNT(*) as c FROM error_logs "
            "WHERE created_at >= datetime('now','-7 days')"
        )

        data["top_queries"] = a._analytics_execute(
            "SELECT query, COUNT(*) as count FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days') AND length(query) BETWEEN 2 AND 80"
            " GROUP BY lower(query) ORDER BY count DESC LIMIT 15"
        )

        data["by_type"] = a._analytics_execute(
            "SELECT search_type as type, COUNT(*) as count FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days')"
            " GROUP BY search_type ORDER BY count DESC"
        )

        today = _dt.date.today()
        raw_daily = a._analytics_execute(
            "SELECT date(created_at) as d, COUNT(*) as count FROM search_logs"
            " WHERE created_at >= datetime('now','-30 days') GROUP BY d ORDER BY d"
        )
        daily_map = {r["d"]: int(r["count"]) for r in raw_daily}
        data["daily"] = [
            {
                "date": (today - _dt.timedelta(days=29 - i)).isoformat(),
                "count": daily_map.get(
                    (today - _dt.timedelta(days=29 - i)).isoformat(), 0
                ),
            }
            for i in range(30)
        ]

        raw_hourly = a._analytics_execute(
            "SELECT hour, COUNT(*) as count FROM search_logs"
            " WHERE created_at >= datetime('now','-7 days') GROUP BY hour"
        )
        hour_map = {int(r["hour"]): int(r["count"]) for r in raw_hourly}
        data["hourly"] = [{"hour": h, "count": hour_map.get(h, 0)} for h in range(24)]

        data["recent_searches"] = a._analytics_execute(
            "SELECT query, search_type as type, result_count as results,"
            " latency_ms, created_at as ts, client_ip, user_agent, device_label, location"
            " FROM search_logs ORDER BY id DESC LIMIT 50"
        )

        try:
            rows = a._users_execute("SELECT COUNT(*) as cnt FROM users")
            data["total_users"] = rows[0]["cnt"] if rows else 0
            rows = a._users_execute(
                "SELECT COUNT(*) as cnt FROM users WHERE created_at >= date('now')"
            )
            data["users_today"] = rows[0]["cnt"] if rows else 0
            rows = a._users_execute(
                "SELECT COUNT(*) as cnt FROM users "
                "WHERE created_at >= datetime('now','-7 days')"
            )
            data["users_week"] = rows[0]["cnt"] if rows else 0
            rows = a._users_execute("SELECT COUNT(*) as cnt FROM user_search_history")
            data["account_history_rows"] = int(rows[0]["cnt"]) if rows else 0
        except Exception:
            data["total_users"] = 0
            data["users_today"] = 0
            data["users_week"] = 0
            data["account_history_rows"] = 0

        data["error_logs"] = a._analytics_execute(
            "SELECT route, level, message, created_at as ts FROM error_logs"
            " ORDER BY id DESC LIMIT 100"
        )

        raw_min = a._analytics_execute(
            "SELECT strftime('%H:%M', created_at) as minute, COUNT(*) as count"
            " FROM search_logs WHERE created_at >= datetime('now','-10 minutes')"
            " GROUP BY minute ORDER BY minute"
        )
        data["per_minute"] = raw_min

        data["live_clients"] = len(a._SSE_CLIENTS)
        data["server_time"] = _dt.datetime.utcnow().isoformat() + "Z"

    except Exception as exc:
        data["error"] = str(exc)
    return jsonify(data)


@admin_bp.route("/admin/api/query-log", endpoint="admin_api_query_log")
def admin_api_query_log():
    """Paginated search log with query text, IP, device, location (admin only)."""
    a = _app()
    err = a._admin_check()
    if err:
        return err
    limit = min(500, max(1, request.args.get("limit", 100, type=int) or 100))
    offset = max(0, request.args.get("offset", 0, type=int) or 0)
    try:
        tot = a._analytics_execute("SELECT COUNT(*) as c FROM search_logs")
        total = int(list(tot[0].values())[0]) if tot else 0
        rows = a._analytics_execute(
            "SELECT id, query, search_type as type, result_count as results, latency_ms,"
            " created_at as ts, client_ip, user_agent, device_label, location"
            " FROM search_logs ORDER BY id DESC LIMIT ? OFFSET ?",
            [limit, offset],
        )
        return jsonify(
            {"total": total, "rows": rows or [], "limit": limit, "offset": offset}
        )
    except Exception as exc:
        return jsonify({"error": str(exc), "total": 0, "rows": []}), 500


@admin_bp.route("/admin/api/account-history", endpoint="admin_api_account_history")
def admin_api_account_history():
    """Paginated rows from user_search_history (queries saved for logged-in accounts)."""
    a = _app()
    err = a._admin_check()
    if err:
        return err
    limit = min(500, max(1, request.args.get("limit", 100, type=int) or 100))
    offset = max(0, request.args.get("offset", 0, type=int) or 0)
    try:
        tot = a._users_execute("SELECT COUNT(*) as cnt FROM user_search_history")
        total = int(tot[0]["cnt"]) if tot else 0
        rows = a._users_execute(
            "SELECT h.id, h.query, h.search_type as type, h.searched_at as ts,"
            " u.id as user_id, u.username, u.email"
            " FROM user_search_history h INNER JOIN users u ON u.id = h.user_id"
            " ORDER BY h.searched_at DESC LIMIT ? OFFSET ?",
            [limit, offset],
        )
        return jsonify(
            {"total": total, "rows": rows or [], "limit": limit, "offset": offset}
        )
    except Exception as exc:
        return jsonify({"error": str(exc), "total": 0, "rows": []}), 500


# ---------------------------------------------------------------------------
# Server-Sent Events stream
# ---------------------------------------------------------------------------


@admin_bp.route("/admin/api/stream", endpoint="admin_api_stream")
def admin_api_stream():
    """Server-Sent Events endpoint — pushes live search events to admin dashboard."""
    a = _app()
    err = a._admin_check()
    if err:
        return err

    client_q: queue.Queue = queue.Queue(maxsize=200)
    with a._SSE_LOCK:
        a._SSE_CLIENTS.append(client_q)

    def generate():
        yield "event: connected\ndata: {\"status\":\"ok\"}\n\n"
        try:
            while True:
                try:
                    data = client_q.get(timeout=25)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with a._SSE_LOCK:
                try:
                    a._SSE_CLIENTS.remove(client_q)
                except ValueError:
                    pass

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


@admin_bp.route("/admin/api/health", endpoint="admin_api_health")
def admin_api_health():
    """Health check — shows DB connectivity, cache state, live clients."""
    a = _app()
    err = a._admin_check()
    if err:
        return err
    health = a._build_health_payload(include_sensitive=True)
    return jsonify(health)


# ---------------------------------------------------------------------------
# AI chat (admin-only)
# ---------------------------------------------------------------------------


@admin_bp.route("/admin/api/chat", methods=["POST"], endpoint="admin_chat")
def admin_chat():
    """AI chatbot for the admin — specialized in abbiey.search."""
    a = _app()
    err = a._admin_check()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    user_message = (body.get("message") or "").strip()
    history = body.get("history") or []
    dashboard_context = body.get("context") or ""

    if not user_message:
        return jsonify({"error": "Please enter a message."}), 400

    system = a._ABBIEY_SYSTEM_PROMPT
    if dashboard_context:
        system += f"\n\n== CURRENT LIVE STATS (from dashboard) ==\n{dashboard_context}"

    messages = [{"role": "system", "content": system}]
    for h in history[-10:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"][:2000]})
    messages.append({"role": "user", "content": user_message})

    ollama_url = a.OLLAMA_BASE_URL.rstrip("/")
    try:
        resp = a._get_http().post(
            f"{ollama_url}/api/chat",
            json={"model": a.OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=30,
        )
        if resp.status_code == 200:
            reply = resp.json().get("message", {}).get("content", "")
            if reply:
                return jsonify({"reply": reply, "source": "ollama"})
    except Exception:
        pass

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    openai_base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if openai_key:
        try:
            resp = a._get_http().post(
                f"{openai_base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {openai_key}"},
                json={"model": openai_model, "messages": messages, "max_tokens": 1200},
                timeout=30,
            )
            if resp.status_code == 200:
                reply = resp.json()["choices"][0]["message"]["content"]
                return jsonify({"reply": reply, "source": "openai"})
        except Exception as exc:
            a.logger.warning("OpenAI chat failed: %s", exc)

    reply = a._abbiey_bot_fallback(user_message, dashboard_context)
    return jsonify({"reply": reply, "source": "builtin"})
