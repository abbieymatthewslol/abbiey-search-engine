"""End-to-end API key flows (real DB lookup, no mocked auth)."""

from __future__ import annotations

import json
import secrets
import uuid
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

import app as app_module
import billing


def _provision_user_and_key():
    suffix = uuid.uuid4().hex[:10]
    rows = app_module._users_execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
        [f"dev_{suffix}", f"dev_{suffix}@example.com", generate_password_hash("x")],
        return_id=True,
    )
    uid = rows[0]["id"]
    token = app_module.ABBIEY_API_KEY_PREFIX + secrets.token_urlsafe(28)
    app_module._users_execute(
        "INSERT INTO api_keys (user_id, label, key_last_four, key_hash) VALUES (?,?,?,?)",
        [uid, "integration", token[-4:], app_module._hash_api_key(token)],
    )
    return uid, token


def test_real_api_key_resolves_user_id():
    uid, token = _provision_user_and_key()
    assert app_module._user_id_from_api_key(token) == uid
    assert app_module._user_id_from_api_key(token + "x") is None


def test_v1_search_with_real_key(client):
    _uid, token = _provision_user_and_key()
    fake = {"results": [{"title": "T", "url": "https://ex.com", "body": "b"}], "has_more": False}
    with patch("app._fetch_results", return_value=fake):
        resp = client.get(
            "/api/v1/search?q=integration",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.get_json()["query"] == "integration"


def test_v1_bots_list_with_real_key(client):
    uid, token = _provision_user_and_key()
    app_module._users_execute(
        "INSERT INTO user_search_bots (user_id, name, allow_hosts, seed_urls, max_depth, max_pages) "
        "VALUES (?,?,?,?,?,?)",
        [uid, "Test bot", '["example.com"]', '["https://example.com/"]', 1, 10],
    )
    resp = client.get("/api/v1/bots", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    bots = resp.get_json().get("bots") or []
    assert len(bots) >= 1
    assert bots[0]["name"] == "Test bot"


def test_user_bookmark_post_with_real_key(client):
    uid, token = _provision_user_and_key()
    resp = client.post(
        "/api/user/bookmarks",
        json={"url": "https://example.com/doc", "title": "Doc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    got = client.get("/api/user/bookmarks", headers={"Authorization": f"Bearer {token}"})
    assert got.status_code == 200
    urls = [b["url"] for b in got.get_json().get("bookmarks") or []]
    assert "https://example.com/doc" in urls


def test_billing_record_event_persists(client):
    uid, _token = _provision_user_and_key()
    billing.configure(app_module._users_execute)
    billing.ensure_schema()
    billing.record_event(user_id=uid, endpoint="/api/v1/search", status_code=200, latency_ms=50)
    rows = app_module._users_execute(
        "SELECT endpoint, status_code FROM api_usage_events WHERE user_id=? ORDER BY id DESC LIMIT 1",
        [uid],
    )
    assert rows
    assert rows[0]["endpoint"] == "/api/v1/search"
    assert int(rows[0]["status_code"]) == 200


def test_billing_skips_5xx_quota():
    uid, _ = _provision_user_and_key()
    billing.configure(app_module._users_execute)
    billing.ensure_schema()
    before = billing.monthly_usage_for_user(uid)["used"]
    billing.record_event(user_id=uid, endpoint="/api/v1/search", status_code=500, latency_ms=1)
    after = billing.monthly_usage_for_user(uid)["used"]
    assert after == before


def test_stripe_webhook_unconfigured(client):
    resp = client.post("/webhooks/stripe", data=b"{}", content_type="application/json")
    assert resp.status_code == 503


def test_stripe_link_customer_by_email():
    uid, _ = _provision_user_and_key()
    email_row = app_module._users_execute("SELECT email FROM users WHERE id=?", [uid])
    email = email_row[0]["email"]
    assert billing.link_stripe_customer_for_email(email, "cus_test_123")
    row = app_module._users_execute("SELECT stripe_customer_id FROM users WHERE id=?", [uid])
    assert row[0].get("stripe_customer_id") == "cus_test_123"
