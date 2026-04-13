"""Custom search bots API — auth and validation (no live crawl)."""

from search_bots import normalize_http_seed


def test_normalize_http_seed_allowlist():
    assert normalize_http_seed("https://docs.example.com/a", ["docs.example.com", "example.com"])
    assert not normalize_http_seed("https://evil.com/", ["example.com"])


def test_search_bots_list_requires_auth(client):
    r = client.get("/api/user/search-bots")
    assert r.status_code == 401


def test_search_bots_create_requires_auth(client):
    r = client.post(
        "/api/user/search-bots",
        json={"name": "x", "allow_hosts": ["example.com"], "seed_urls": ["https://example.com/"]},
    )
    assert r.status_code == 401
