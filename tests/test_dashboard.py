"""Dashboard page and API personalization."""

from __future__ import annotations

import uuid

from werkzeug.security import generate_password_hash

import app as app_module


def _login_test_user(client, prefix: str = "dashpage") -> int:
    suffix = uuid.uuid4().hex[:10]
    rows = app_module._users_execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
        [f"{prefix}_{suffix}", f"{prefix}_{suffix}@example.com", generate_password_hash("password123")],
        return_id=True,
    )
    uid = rows[0]["id"]
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return uid


def test_dashboard_page_renders_for_guest(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b"dashboard-page" in resp.data
    assert b"Sign in" in resp.data
    assert b"dashboard.js" in resp.data


def test_dashboard_page_renders_for_logged_in_user(client):
    _login_test_user(client, "dashguest")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert b'data-logged-in="true"' in resp.data
    assert b"widget-searches" in resp.data
    assert b"widget-bookmarks" in resp.data


def test_dashboard_api_requires_auth(client):
    resp = client.get("/api/user/dashboard")
    assert resp.status_code == 401


def test_dashboard_api_entity_hints_from_email_query(client):
    uid = _login_test_user(client, "entityhint")
    app_module._users_execute(
        "INSERT INTO user_search_history (user_id, query, search_type) VALUES (?,?,?)",
        [uid, "check user@example.com breach", "email"],
    )
    resp = client.get("/api/user/dashboard")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert any(h.get("type") == "email" for h in data.get("entity_hints", []))
