"""Tests for the public /api/v1 developer API."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import app as app_module
import api_v1 as _apiv1
import billing


VALID_KEY = "abb_sk_live_" + ("x" * 40)
INVALID_KEY = "abb_sk_live_bogus"


@pytest.fixture
def fake_key(monkeypatch):
    """Patch _user_id_from_api_key so VALID_KEY maps to user 1, everything else to None."""

    def _lookup(token: str):
        if token == VALID_KEY:
            return 1
        return None

    monkeypatch.setattr(app_module, "_user_id_from_api_key", _lookup)
    yield


def test_v1_health_is_public(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("api_version") == "1"
    assert "data_region" in body


def test_v1_search_rejects_missing_auth(client):
    resp = client.get("/api/v1/search?q=hello")
    assert resp.status_code == 401
    assert resp.get_json().get("error") == "unauthorized"


def test_v1_search_rejects_bad_key(client, fake_key):
    resp = client.get(
        "/api/v1/search?q=hello",
        headers={"Authorization": f"Bearer {INVALID_KEY}"},
    )
    assert resp.status_code == 401
    assert resp.get_json().get("error") == "invalid_api_key"


def test_v1_search_requires_query(client, fake_key):
    resp = client.get(
        "/api/v1/search",
        headers={"Authorization": f"Bearer {VALID_KEY}"},
    )
    assert resp.status_code == 400
    assert resp.get_json().get("error") == "missing_query"


def test_v1_search_rejects_bad_type(client, fake_key):
    resp = client.get(
        "/api/v1/search?q=hi&type=bogus",
        headers={"Authorization": f"Bearer {VALID_KEY}"},
    )
    assert resp.status_code == 400
    assert resp.get_json().get("error") == "unsupported_type"


def test_v1_search_happy_path_records_usage(client, fake_key):
    fake_results = {
        "results": [
            {"title": "Doc", "url": "https://example.com/a", "body": "body", "source": "example.com"}
        ],
        "has_more": False,
        "sources": [],
        "provider_sources": ["ddg"],
        "cache_state": "fresh_hit",
        "served_stale": False,
        "refreshing": False,
        "degraded": False,
        "degraded_reasons": [],
        "fetched_at": "2026-05-24T10:00:00Z",
        "expires_at": "2026-05-24T10:10:00Z",
    }
    recorded: list[tuple] = []

    def _spy_record(user_id, endpoint, status_code, latency_ms):
        recorded.append((user_id, endpoint, status_code))

    with patch("app._fetch_results", return_value=fake_results), \
         patch.object(billing, "record_event", side_effect=_spy_record):
        resp = client.get(
            "/api/v1/search?q=hello",
            headers={"Authorization": f"Bearer {VALID_KEY}"},
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 1
    assert body["query"] == "hello"
    assert body["results"][0]["url"] == "https://example.com/a"
    assert body["provider_sources"] == ["ddg"]
    assert body["cache_state"] == "fresh_hit"
    assert body["served_stale"] is False
    assert body["degraded"] is False
    assert recorded and recorded[0][0] == 1
    assert recorded[0][1] == "/api/v1/search"
    assert recorded[0][2] == 200


def test_openapi_spec_lists_v1_endpoints(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["openapi"].startswith("3.")
    assert "/search" in body["paths"]
    assert "/health" in body["paths"]
    assert "/bots" in body["paths"]
    assert "/reverse-image" in body["paths"]


def test_api_docs_page_renders(client):
    resp = client.get("/api/v1/docs")
    assert resp.status_code == 200
    assert b"redoc" in resp.data.lower() or b"spec-url" in resp.data.lower()


def test_billing_record_event_without_stripe_is_noop(monkeypatch):
    """Recording usage must never blow up even without a Stripe key / DB."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    # No exec configured; record_event should swallow the error.
    billing._exec = None
    billing.record_event(user_id=1, endpoint="/api/v1/search", status_code=200, latency_ms=123)
