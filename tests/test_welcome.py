"""First-visit /welcome onboarding and root redirect."""

import pytest


def test_index_redirects_to_welcome_when_not_skipped(monkeypatch, client):
    monkeypatch.setenv("ABBIEY_SKIP_WELCOME_SCREEN", "0")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/welcome" in (resp.headers.get("Location") or "")


def test_vercel_root_defaults_to_search_when_skip_unset(monkeypatch, client):
    """Production sets VERCEL; without explicit welcome opt-in, / should hit the search UI."""
    monkeypatch.delenv("ABBIEY_SKIP_WELCOME_SCREEN", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 301
    assert "/search" in (resp.headers.get("Location") or "")


def test_welcome_page_renders_onboarding(client, monkeypatch):
    monkeypatch.setenv("ABBIEY_SKIP_WELCOME_SCREEN", "0")
    resp = client.get("/welcome")
    assert resp.status_code == 200
    assert b"welcome-steps" in resp.data
    assert b"Continue with Google" in resp.data or b"Create account with email" in resp.data


def test_welcome_dismiss_sets_cookie_so_root_goes_to_search(client, monkeypatch):
    monkeypatch.setenv("ABBIEY_SKIP_WELCOME_SCREEN", "0")
    client.get("/welcome/dismiss")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 301
    loc = resp.headers.get("Location") or ""
    assert "/search" in loc
