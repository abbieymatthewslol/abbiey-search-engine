"""Tests for community / refund / status / changelog / docs pages."""

from __future__ import annotations


def test_community_page_renders(client):
    resp = client.get("/community")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", "replace")
    assert "Community" in body
    assert "GitHub" in body
    assert "refunds@abbieysearch.com" in body


def test_refund_page_renders(client):
    resp = client.get("/refund")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", "replace")
    assert "14" in body  # 14-day refund
    assert "refunds@abbieysearch.com" in body


def test_status_page_renders(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", "replace")
    assert "Service status" in body
    assert "/health" in body


def test_changelog_route_renders(client):
    resp = client.get("/changelog")
    assert resp.status_code == 200


def test_docs_page_deep_web_renders(client):
    resp = client.get("/docs/deep-web")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", "replace")
    assert "Ahmia" in body


def test_docs_page_api_renders(client):
    resp = client.get("/docs/api")
    assert resp.status_code == 200


def test_docs_page_unknown_slug_404s(client):
    resp = client.get("/docs/definitely-not-a-real-doc")
    assert resp.status_code == 404


def test_privacy_page_mentions_jurisdiction(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", "replace")
    assert "data-jurisdiction" in body
    assert "Supabase" in body


def test_footer_has_new_links(client):
    resp = client.get("/privacy")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8", "replace")
    assert "/refund" in body
    assert "/community" in body
    assert "/status" in body
    assert "/changelog" in body
