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
