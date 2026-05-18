"""Tests for the extended /health feature-probe payload."""

from __future__ import annotations

from unittest.mock import patch


def test_public_health_has_feature_probes(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    features = body.get("features") or {}
    for key in ("search", "image_upload", "bots", "deep_web", "api_v1"):
        assert key in features, f"missing probe: {key}"
        entry = features[key]
        assert "state" in entry
        assert entry["state"] in {"ok", "degraded", "down"}


def test_health_aggregate_degrades_when_any_feature_down(client):
    with patch("app._feature_probe_search", return_value={"state": "down", "reason": "test"}):
        resp = client.get("/health")
    body = resp.get_json()
    assert body["status"] == "degraded"


def test_health_includes_data_region(client):
    resp = client.get("/health")
    body = resp.get_json()
    assert "data_region" in body


def test_health_image_upload_probe_ok_when_storage_configured(client, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc_key_xxx")
    resp = client.get("/health")
    features = resp.get_json().get("features") or {}
    assert features["image_upload"]["state"] == "ok"


def test_health_image_upload_probe_degraded_without_storage_or_site_url(client, monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SITE_URL", raising=False)
    resp = client.get("/health")
    features = resp.get_json().get("features") or {}
    assert features["image_upload"]["state"] in {"degraded", "down"}


def test_healthz_returns_200_without_supabase(client, monkeypatch):
    """Without SUPABASE_DB_URL configured, /healthz should still return 200."""
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["supabase"] == "not_configured"
    assert "ts" in body
    assert "storage" in body


def test_healthz_supabase_ok_when_pg_responds(client, monkeypatch):
    """When Supabase IS configured and responding, supabase key should be 'ok'."""
    with patch("app._SUPABASE_DB_URL", "postgresql://x:y@pooler.supabase.com:6543/postgres"), \
         patch("app._SUPABASE_DB_READY", True), \
         patch("app._pg_execute", return_value=[{"ok": 1}]):
        resp = client.get("/healthz")
    body = resp.get_json()
    assert body["supabase"] == "ok"
    assert resp.status_code == 200


def test_healthz_503_when_supabase_configured_but_unreachable(client):
    """503 is returned when SUPABASE_DB_URL is set but _SUPABASE_DB_READY is False."""
    with patch("app._SUPABASE_DB_URL", "postgresql://x:y@pooler.supabase.com:6543/postgres"), \
         patch("app._SUPABASE_DB_READY", False):
        resp = client.get("/healthz")
    body = resp.get_json()
    assert resp.status_code == 503
    assert body["status"] == "degraded"
    assert body["supabase"] == "unreachable"


def test_healthz_redis_not_configured(client):
    """Without Upstash env vars, redis field should be 'not_configured'."""
    with patch("app._UPSTASH_URL", ""), patch("app._UPSTASH_TOKEN", ""):
        resp = client.get("/healthz")
    body = resp.get_json()
    assert body["redis"] == "not_configured"
