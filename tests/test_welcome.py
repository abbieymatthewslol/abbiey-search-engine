"""First-visit /welcome onboarding and root homepage behavior."""

import pytest


def test_index_stays_on_homepage_when_welcome_not_skipped(monkeypatch, client):
    monkeypatch.setenv("ABBIEY_SKIP_WELCOME_SCREEN", "0")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert b'id="search-input"' in resp.data


def test_vercel_root_defaults_to_homepage_when_skip_unset(monkeypatch, client):
    """Production sets VERCEL; without explicit welcome opt-in, / should render the search homepage directly."""
    monkeypatch.delenv("ABBIEY_SKIP_WELCOME_SCREEN", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert b'id="search-input"' in resp.data


def test_welcome_page_renders_onboarding(client, monkeypatch):
    monkeypatch.setenv("ABBIEY_SKIP_WELCOME_SCREEN", "0")
    resp = client.get("/welcome")
    assert resp.status_code == 200
    assert b"welcome-steps" in resp.data
    assert b"Continue with Google" in resp.data or b"Create account with email" in resp.data
    assert b"Privacy choices" in resp.data
    assert b"Allow precise location for nearby results" in resp.data


def test_welcome_exposes_detected_country_for_phone_localization(client, monkeypatch):
    monkeypatch.setenv("ABBIEY_SKIP_WELCOME_SCREEN", "0")
    resp = client.get("/welcome", headers={"X-Vercel-IP-Country": "AU"})
    assert resp.status_code == 200
    assert b'data-phone-placeholder-localize="true"' in resp.data


def test_blank_search_defaults_region_from_detected_country(client):
    resp = client.get("/search", headers={"X-Vercel-IP-Country": "GB"})
    assert resp.status_code == 200
    assert b'id="region-input" value="uk-en"' in resp.data
    assert b'id="lang-input" value="en"' in resp.data


def test_welcome_dismiss_sets_cookie_so_root_stays_homepage(client, monkeypatch):
    monkeypatch.setenv("ABBIEY_SKIP_WELCOME_SCREEN", "0")
    dismiss = client.get("/welcome/dismiss", follow_redirects=False)
    assert dismiss.status_code == 302
    assert (dismiss.headers.get("Location") or "").endswith("/")
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
    assert b'id="search-input"' in resp.data
