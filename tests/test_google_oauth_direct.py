"""Direct Google OAuth (no Supabase Auth)."""

from unittest.mock import patch

import google_oauth


def test_google_oauth_configured_requires_both_secrets(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    assert google_oauth.google_oauth_configured() is False
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    assert google_oauth.google_oauth_configured() is False
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "sec")
    assert google_oauth.google_oauth_configured() is True


def test_google_oauth_start_redirects_to_google(client):
    with patch("app._GOOGLE_OAUTH_ENABLED", True), patch(
        "app._google_build_authorize_url", return_value="https://accounts.google.com/o/oauth2/v2/auth?x=1"
    ):
        r = client.get("/auth/google?next=/search")
    assert r.status_code == 302
    assert "accounts.google.com" in (r.headers.get("Location") or "")


def test_google_oauth_start_disabled(client):
    with patch("app._GOOGLE_OAUTH_ENABLED", False):
        r = client.get("/auth/google", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.headers.get("Location") or "")


def test_google_oauth_callback_happy_path_sets_session_and_device_cookie(client):
    token_data = {"access_token": "atok"}
    profile = {"sub": "gid-123", "email": "goog@example.com", "name": "Goog User"}

    def fake_sync(email, display_name="", phone=None, auth_marker="supabase_auth"):
        assert email == "goog@example.com"
        assert auth_marker == "google_oauth"
        return 501

    def fake_users(sql, args=None, return_id=False):
        s = (sql or "").lower()
        if "oauth_user_binding" in s and "select" in s:
            return []
        if "oauth_user_binding" in s and "insert" in s:
            assert args[0] == 501
            assert args[1] == "google_direct:gid-123"
            assert args[2] == "gid-123"
            return []
        return []

    with client.session_transaction() as sess:
        sess["google_oauth_state"] = "state-abc"
        sess["google_oauth_next"] = "/search"

    with patch("app._GOOGLE_OAUTH_ENABLED", True), patch(
        "app._google_exchange_code", return_value=token_data
    ), patch("app._google_fetch_userinfo", return_value=profile), patch(
        "app._sync_supabase_auth_user", side_effect=fake_sync
    ), patch(
        "app._users_execute", side_effect=fake_users
    ):
        r = client.get("/auth/google/callback?code=abc&state=state-abc", follow_redirects=False)

    assert r.status_code == 302
    assert (r.headers.get("Location") or "").endswith("/search")
    set_cookies = r.headers.getlist("Set-Cookie")
    assert any("abbiey_auth_device=" in c for c in set_cookies)
    with client.session_transaction() as sess:
        assert sess.get("user_id") == 501


def test_login_shows_direct_google_link_when_enabled(client):
    with patch("app._GOOGLE_OAUTH_ENABLED", True), patch("app._SUPABASE_AUTH_ENABLED", False):
        r = client.get("/login")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "/auth/google" in body
    assert "Continue with Google" in body
    assert "vendor/supabase.min.js" not in body
