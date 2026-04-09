"""Auth pages must extend auth_base.html so layout/CSS stay aligned with /search."""

import pytest


_AUTH_MARKERS = (
    b"page-auth",
    b"abbiey-auth-main",
    b"auth-panel",
    b"auth-back-search",
)


@pytest.mark.parametrize("path", ["/signup", "/login", "/verify-email", "/welcome"])
def test_auth_pages_use_shared_layout_contract(client, path):
    r = client.get(path)
    assert r.status_code == 200
    for needle in _AUTH_MARKERS:
        assert needle in r.data, f"missing {needle!r} on {path}"


def test_signup_still_renders_form_fields(client):
    r = client.get("/signup")
    assert r.status_code == 200
    assert b'name="email"' in r.data
    assert b'name="password"' in r.data
    # Either legacy form id or Supabase form id
    assert b"signup-form" in r.data or b"sb-signup-form" in r.data
