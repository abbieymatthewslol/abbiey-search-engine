"""Supabase OAuth callback: JWT validation via GoTrue and Google + device binding."""

import hashlib
import secrets
from unittest.mock import patch


def test_auth_callback_requires_access_token_when_supabase_enabled(client):
    with patch("app._SUPABASE_AUTH_ENABLED", True):
        r = client.post("/auth/callback", json={"email": "x@y.com", "display_name": "X"})
    assert r.status_code == 401
    assert r.get_json().get("error") == "invalid_token"


def test_auth_callback_first_google_login_sets_device_cookie(client):
    sb_user = {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "goog@example.com",
        "user_metadata": {"full_name": "G"},
        "identities": [{"provider": "google", "identity_data": {"sub": "gid-aaa"}}],
    }

    def fetch_tok(tok):
        return sb_user if tok == "tok1" else None

    def fake_sync(email, display_name, phone_e164=None):
        assert email == "goog@example.com"
        return 101

    def fake_users(sql, args=None, return_id=False):
        s = (sql or "").lower()
        if "oauth_user_binding" in s and "select" in s:
            return []
        if "oauth_user_binding" in s and "insert" in s:
            assert args[0] == 101
            assert args[1] == sb_user["id"]
            assert args[2] == "gid-aaa"
            assert len(args[3]) == 64
            return []
        return []

    with patch("app._SUPABASE_AUTH_ENABLED", True), patch(
        "app._supabase_fetch_user_from_access_token", side_effect=fetch_tok
    ), patch("app._sync_supabase_auth_user", side_effect=fake_sync), patch(
        "app._users_execute", side_effect=fake_users
    ):
        r = client.post(
            "/auth/callback",
            json={"access_token": "tok1", "email": "goog@example.com"},
        )
    assert r.status_code == 200
    assert r.get_json().get("ok") is True
    set_cookies = r.headers.getlist("Set-Cookie")
    assert any("abbiey_auth_device=" in c for c in set_cookies)


def test_auth_callback_device_mismatch_when_binding_exists(client):
    secret = secrets.token_urlsafe(34)
    dhash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    binding = {
        "user_id": 202,
        "supabase_auth_uid": "11111111-1111-1111-1111-111111111111",
        "google_sub": "gid-aaa",
        "device_secret_hash": dhash,
    }
    sb_user = {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "goog@example.com",
        "identities": [{"provider": "google", "identity_data": {"sub": "gid-aaa"}}],
    }

    def fetch_tok(tok):
        return sb_user if tok else None

    def fake_sync(email, display_name, phone_e164=None):
        return 202

    def fake_users(sql, args=None, return_id=False):
        s = (sql or "").lower()
        if "oauth_user_binding" in s and "select" in s:
            return [dict(binding)]
        return []

    with patch("app._SUPABASE_AUTH_ENABLED", True), patch(
        "app._supabase_fetch_user_from_access_token", side_effect=fetch_tok
    ), patch("app._sync_supabase_auth_user", side_effect=fake_sync), patch(
        "app._users_execute", side_effect=fake_users
    ):
        r = client.post("/auth/callback", json={"access_token": "tok", "email": "goog@example.com"})
    assert r.status_code == 403
    assert r.get_json().get("error") == "device_mismatch"


def test_auth_callback_wrong_google_when_binding_exists(client):
    secret = secrets.token_urlsafe(34)
    dhash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    binding = {
        "user_id": 202,
        "supabase_auth_uid": "11111111-1111-1111-1111-111111111111",
        "google_sub": "gid-aaa",
        "device_secret_hash": dhash,
    }
    sb_user = {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "goog@example.com",
        "identities": [{"provider": "google", "identity_data": {"sub": "gid-other"}}],
    }

    def fake_users(sql, args=None, return_id=False):
        s = (sql or "").lower()
        if "oauth_user_binding" in s and "select" in s:
            return [dict(binding)]
        return []

    with patch("app._SUPABASE_AUTH_ENABLED", True), patch(
        "app._supabase_fetch_user_from_access_token", lambda _t: sb_user
    ), patch("app._sync_supabase_auth_user", lambda *a, **k: 202), patch(
        "app._users_execute", side_effect=fake_users
    ):
        r = client.post("/auth/callback", json={"access_token": "tok", "email": "goog@example.com"})
    assert r.status_code == 403
    assert r.get_json().get("error") == "wrong_google_account"


def test_profile_redirects_when_device_cookie_missing(client):
    secret = secrets.token_urlsafe(34)
    dhash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    row = {
        "user_id": 303,
        "supabase_auth_uid": "x",
        "google_sub": "g",
        "device_secret_hash": dhash,
    }
    with client.session_transaction() as sess:
        sess["user_id"] = 303
    with patch("app._oauth_binding_row_for_user", return_value=row):
        r = client.get("/profile", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in (r.headers.get("Location") or "")
