"""Email verification + OTP on signup."""

import uuid
from unittest.mock import patch

import pytest


@pytest.fixture
def unique_creds():
    u = uuid.uuid4().hex[:8]
    return {
        "username": f"vuser_{u}",
        "email": f"vuser_{u}@example.com",
        "password": "password123",
        "confirm_password": "password123",
    }


def test_signup_redirects_to_verify_email(client, unique_creds):
    with patch("app._send_signup_verification_email", return_value=True):
        r = client.post("/signup", data=unique_creds)
    assert r.status_code == 302
    loc = r.headers.get("Location", "")
    assert "/verify-email" in loc
    assert unique_creds["email"] in loc


def test_signup_then_otp_verifies_and_logs_in(client, unique_creds):
    import app as app_mod

    otp_holder: list[tuple[str, str]] = []
    real_set = app_mod._set_verification_challenge

    def wrap(uid):
        o, t = real_set(uid)
        otp_holder.append((o, t))
        return o, t

    with patch.object(app_mod, "_set_verification_challenge", side_effect=wrap):
        with patch.object(app_mod, "_send_signup_verification_email", return_value=True):
            r0 = client.post("/signup", data=unique_creds)
    assert r0.status_code == 302
    assert len(otp_holder) == 1
    otp, _vtok = otp_holder[0]

    r1 = client.post(
        "/verify-email",
        data={"email": unique_creds["email"], "code": otp},
        follow_redirects=False,
    )
    assert r1.status_code == 302

    r_profile = client.get("/profile")
    assert r_profile.status_code == 200


def test_login_rejects_unverified(client, unique_creds):
    import app as app_mod

    real_set = app_mod._set_verification_challenge

    def wrap(uid):
        return real_set(uid)

    with patch.object(app_mod, "_set_verification_challenge", side_effect=wrap):
        with patch.object(app_mod, "_send_signup_verification_email", return_value=True):
            client.post("/signup", data=unique_creds)

    r = client.post(
        "/login",
        data={
            "identifier": unique_creds["email"],
            "password": unique_creds["password"],
        },
    )
    assert r.status_code == 200
    assert b"verify your email" in r.data.lower()
