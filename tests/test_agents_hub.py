"""AI agents hub and legacy /bots redirect."""


def test_agents_page_renders(client):
    r = client.get("/agents")
    assert r.status_code == 200
    assert b"AI agents" in r.data


def test_bots_legacy_redirects_to_agents(client):
    r = client.get("/bots", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert "/agents" in (r.headers.get("Location") or "")


def test_signup_accepts_next_for_profile_anchor(client):
    r = client.get("/signup", query_string={"next": "/profile#search-bots"})
    assert r.status_code == 200
    assert b'name="next"' in r.data
    assert b"/profile#search-bots" in r.data


def test_verify_email_page_preserves_next(client):
    r = client.get(
        "/verify-email",
        query_string={"email": "x@example.com", "new": "1", "next": "/profile#search-bots"},
    )
    assert r.status_code == 200
    assert b'name="next"' in r.data
