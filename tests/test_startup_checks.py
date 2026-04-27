"""Tests for startup_checks.py - the fail-fast production env guard."""

from __future__ import annotations

import os

import pytest

import startup_checks


def _clear_prod_env(monkeypatch):
    for k in ("FLASK_ENV", "ENV", "VERCEL", "RAILWAY_ENVIRONMENT_NAME"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("RUNNING_PYTEST", raising=False)
    monkeypatch.delenv("ABBIEY_SKIP_STARTUP_CHECKS", raising=False)
    # Clear every gate env so conditional requirements don't leak from a real .env
    for _req, gate in startup_checks._CONDITIONAL:
        monkeypatch.delenv(gate, raising=False)
        monkeypatch.delenv(_req.name, raising=False)


def test_is_production_detects_vercel(monkeypatch):
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    assert startup_checks.is_production() is True


def test_is_production_detects_flask_env(monkeypatch):
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("FLASK_ENV", "production")
    assert startup_checks.is_production() is True


def test_is_production_defaults_false(monkeypatch):
    _clear_prod_env(monkeypatch)
    assert startup_checks.is_production() is False


def test_assert_production_env_raises_when_missing(monkeypatch):
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    for r in startup_checks._REQUIRED:
        monkeypatch.delenv(r.name, raising=False)
    with pytest.raises(SystemExit) as ei:
        startup_checks.assert_production_env()
    assert ei.value.code == 78


def test_assert_production_env_passes_when_all_set(monkeypatch):
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    for r in startup_checks._REQUIRED:
        monkeypatch.setenv(r.name, "fake")
    startup_checks.assert_production_env()


def test_skip_flag_bypasses_checks(monkeypatch):
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    for r in startup_checks._REQUIRED:
        monkeypatch.delenv(r.name, raising=False)
    monkeypatch.setenv("ABBIEY_SKIP_STARTUP_CHECKS", "1")
    startup_checks.assert_production_env()


def test_pytest_env_is_auto_skipped(monkeypatch):
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("RUNNING_PYTEST", "1")
    for r in startup_checks._REQUIRED:
        monkeypatch.delenv(r.name, raising=False)
    startup_checks.assert_production_env()


def test_summarize_config_reports_presence(monkeypatch):
    _clear_prod_env(monkeypatch)
    for r in startup_checks._REQUIRED:
        monkeypatch.setenv(r.name, "x")
    out = startup_checks.summarize_config()
    assert out["required_total"] == out["required_present"]
    assert out["required_missing"] == []
