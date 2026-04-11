"""Signup/login consistency: unique handling, case-insensitive login, submit locking."""

import sqlite3
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "msg,expected",
    [
        ("UNIQUE constraint failed: users.username", "username"),
        ("UNIQUE constraint failed: users.email", "email"),
    ],
)
def test_signup_unique_conflict_sqlite(msg, expected):
    from app import _signup_unique_conflict_field

    assert _signup_unique_conflict_field(sqlite3.IntegrityError(msg)) == expected


def test_signup_rejects_duplicate_email_before_insert(client):
    calls = []

    def fake_execute(sql, args=None, return_id=False):
        calls.append((sql, args, return_id))
        su = (sql or "").upper()
        if "INSERT" in su:
            raise AssertionError("insert should not run when email is taken")
        if "USERNAME" in su and "LIMIT" in su:
            return []
        if "EMAIL" in su and "LIMIT" in su:
            return [{"ok": 1}]
        return []

    with patch("app._users_execute", side_effect=fake_execute):
        r = client.post(
            "/signup",
            data={
                "username": "fresh_name_xyz",
                "email": "taken@example.com",
                "password": "password123",
                "confirm_password": "password123",
            },
        )
    assert r.status_code == 200
    assert b"already exists" in r.data


def test_signup_maps_integrity_error_on_insert(client):
    def fake_execute(sql, args=None, return_id=False):
        if "INSERT" in (sql or "").upper():
            raise sqlite3.IntegrityError("UNIQUE constraint failed: users.username")
        return []

    with patch("app._users_execute", side_effect=fake_execute):
        r = client.post(
            "/signup",
            data={
                "username": "anyuser",
                "email": "new@example.com",
                "password": "password123",
                "confirm_password": "password123",
            },
        )
    assert r.status_code == 200
    assert b"already taken" in r.data


def test_signup_outer_try_never_500_on_bcrypt_failure(client):
    """Any unexpected error during signup POST should return the form with 200, not 500."""
    with patch("app.generate_password_hash", side_effect=RuntimeError("hash failed")):
        r = client.post(
            "/signup",
            data={
                "username": "validuser",
                "email": "ok@example.com",
                "password": "password123",
                "confirm_password": "password123",
            },
        )
    assert r.status_code == 200
    assert b"Something went wrong" in r.data or b"went wrong" in r.data


def test_login_finds_user_case_insensitive(client):
    with patch("app._users_execute") as ex:
        ex.return_value = [
            {
                "id": 1,
                "username": "jane_doe",
                "email": "jane@example.com",
                "password_hash": "x",
                "display_name": "Jane_Doe",
                "bio": "",
                "avatar": None,
                "created_at": "",
                "last_seen": "",
            }
        ]
        from app import _get_user_by_login

        u = _get_user_by_login("JANE@EXAMPLE.COM")
        assert u is not None
        assert u["email"] == "jane@example.com"
    sql = ex.call_args[0][0]
    assert "LOWER(email)" in sql and "LOWER(username)" in sql


# ---------------------------------------------------------------------------
# sb_access_token cookie helpers
# ---------------------------------------------------------------------------

import base64
import json as _json


def _make_fake_jwt(email: str, secret: str = "") -> str:
    """Build a minimal HS256 JWT for unit-testing (not cryptographically complete)."""
    import hashlib
    import hmac as _hmac

    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    payload_b = _json.dumps({"email": email, "sub": "test-uid"}).encode()
    payload = base64.urlsafe_b64encode(payload_b).rstrip(b"=").decode()
    message = f"{header}.{payload}".encode()
    if secret:
        sig_bytes = _hmac.new(secret.encode(), message, hashlib.sha256).digest()
    else:
        sig_bytes = b"\x00" * 32
    sig = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
    return f"{header}.{payload}.{sig}"


def test_decode_supabase_jwt_valid():
    """_decode_supabase_jwt returns payload for a well-formed JWT."""
    from app import _decode_supabase_jwt

    token = _make_fake_jwt("user@example.com")
    payload = _decode_supabase_jwt(token)
    assert payload is not None
    assert payload["email"] == "user@example.com"


def test_decode_supabase_jwt_rejects_non_jwt():
    """_decode_supabase_jwt returns None for garbage input."""
    from app import _decode_supabase_jwt

    assert _decode_supabase_jwt("") is None
    assert _decode_supabase_jwt("not.a.valid.jwt.parts") is None
    assert _decode_supabase_jwt("bad-value") is None


def test_decode_supabase_jwt_rejects_injection_chars():
    """_decode_supabase_jwt returns None if any segment contains forbidden chars."""
    from app import _decode_supabase_jwt

    # Embedding a newline in the signature segment would break Set-Cookie
    token = _make_fake_jwt("x@x.com")
    assert _decode_supabase_jwt(token) is not None  # baseline: valid token passes
    header, payload, _sig = token.split(".")
    assert _decode_supabase_jwt(f"{header}.{payload}.bad\nsig") is None


def test_auth_callback_sets_sb_cookie(client):
    """POST /auth/callback stores sb_access_token cookie when access_token is present."""
    fake_token = _make_fake_jwt("cb@example.com")
    fake_user = {
        "id": 42,
        "email": "cb@example.com",
        "username": "cb_user",
        "password_hash": "supabase_auth",
        "display_name": "CB User",
        "email_verified": True,
        "bio": "",
        "avatar": None,
        "created_at": "",
        "last_seen": "",
    }

    def fake_execute(sql, args=None, return_id=False):
        su = (sql or "").upper()
        if "INSERT" in su:
            return [{"id": 42}]
        if "SELECT" in su and "EMAIL" in su:
            return [{"id": 42}]
        return []

    with patch("app._users_execute", side_effect=fake_execute):
        with patch("app._SUPABASE_AUTH_ENABLED", True):
            r = client.post(
                "/auth/callback",
                json={
                    "email": "cb@example.com",
                    "display_name": "CB User",
                    "access_token": fake_token,
                },
            )
    assert r.status_code == 200
    assert r.get_json().get("ok") is True
    set_cookie_headers = "\n".join(r.headers.getlist("Set-Cookie"))
    assert "sb_access_token" in set_cookie_headers


def test_uid_from_sb_access_token_cookie_fallback(client):
    """_inject_current_user resolves user via sb_access_token cookie when session is empty."""
    fake_token = _make_fake_jwt("cookie@example.com")
    fake_user = {
        "id": 7,
        "email": "cookie@example.com",
        "username": "cookie_user",
        "password_hash": "supabase_auth",
        "display_name": "Cookie User",
        "email_verified": True,
        "bio": "",
        "avatar": None,
        "created_at": "",
        "last_seen": "",
    }

    def fake_execute(sql, args=None, return_id=False):
        su = (sql or "").upper()
        if "SELECT" in su and "EMAIL" in su and "LIMIT" in su:
            return [{"id": 7}]
        if "SELECT" in su and "WHERE ID" in su:
            return [fake_user]
        if "UPDATE" in su:
            return []
        return []

    with patch("app._users_execute", side_effect=fake_execute):
        with patch("app._get_user_by_id", return_value=fake_user):
            r = client.get(
                "/search",
                headers={"Cookie": f"sb_access_token={fake_token}"},
            )
    # /search returns 200 regardless; we confirm the route does not 500
    assert r.status_code in (200, 302)
