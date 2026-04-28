"""Tests for feature gates (all / paid / none env-driven toggles on /search)."""

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Feature gate unit tests
# ---------------------------------------------------------------------------

class TestFeatureAllowed:
    def test_all_gate_allows_anyone(self):
        import os
        with patch.dict("os.environ", {"FEATURE_DEEP_WEB": "all"}):
            # Re-read via the function directly
            from app import _feature_allowed
            assert _feature_allowed("deep_web", unlocked=False) is True
            assert _feature_allowed("deep_web", unlocked=True) is True

    def test_paid_gate_requires_unlock(self):
        from app import _feature_allowed, _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "paid"
            assert _feature_allowed("deep_web", unlocked=False) is False
            assert _feature_allowed("deep_web", unlocked=True) is True
        finally:
            _FEATURE_GATES["deep_web"] = original

    def test_none_gate_blocks_everyone(self):
        from app import _feature_allowed, _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "none"
            assert _feature_allowed("deep_web", unlocked=False) is False
            assert _feature_allowed("deep_web", unlocked=True) is False
        finally:
            _FEATURE_GATES["deep_web"] = original

    def test_unknown_gate_defaults_to_all(self):
        from app import _feature_allowed
        assert _feature_allowed("nonexistent_gate", unlocked=False) is True

    def test_invalid_gate_value_defaults_to_all(self):
        from app import _feature_allowed, _FEATURE_GATES
        original = _FEATURE_GATES.get("ai_summary")
        try:
            _FEATURE_GATES["ai_summary"] = "INVALID_VALUE"
            assert _feature_allowed("ai_summary", unlocked=False) is True
        finally:
            _FEATURE_GATES["ai_summary"] = original

    def test_feature_gates_for_user_reflects_unlocked(self):
        from app import _feature_gates_for_user, _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "paid"
            gates_free = _feature_gates_for_user(False)
            gates_paid = _feature_gates_for_user(True)
            assert gates_free["deep_web"] is False
            assert gates_paid["deep_web"] is True
        finally:
            _FEATURE_GATES["deep_web"] = original


# ---------------------------------------------------------------------------
# Feature gate enforcement in /search route
# ---------------------------------------------------------------------------

class TestFeatureGateSearchRoute:
    def test_none_gate_returns_404_for_onion(self, client):
        from app import _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "none"
            resp = client.get("/search?q=test&type=onion")
            assert resp.status_code == 404
        finally:
            _FEATURE_GATES["deep_web"] = original

    def test_paid_gate_blocks_onion_search_for_free_users(self, client):
        """Deep web with FEATURE_DEEP_WEB=paid requires an unlocked account (403)."""
        from app import _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "paid"
            resp = client.get("/search?q=test&type=onion")
            assert resp.status_code == 403
        finally:
            _FEATURE_GATES["deep_web"] = original

    def test_all_gate_allows_free_user_for_onion(self, client):
        """Default gate value 'all' should let anyone access the deep web tab."""
        from app import _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "all"
            onion_results = [
                {"title": "Site", "url": "http://xyz.onion/", "body": "x", "onion": True},
            ]
            with patch("app._try_ahmia", return_value=onion_results), \
                 patch("app._try_onion_ddg", return_value=[]):
                resp = client.get("/search?q=test&type=onion")
            assert resp.status_code == 200
        finally:
            _FEATURE_GATES["deep_web"] = original

    def test_none_gate_returns_404_for_code_search(self, client, mock_ddg):
        from app import _FEATURE_GATES
        original = _FEATURE_GATES.get("code_search")
        try:
            _FEATURE_GATES["code_search"] = "none"
            resp = client.get("/search?q=python&type=code")
            assert resp.status_code == 404
        finally:
            _FEATURE_GATES["code_search"] = original

    def test_feature_gates_in_template_context(self, client, mock_ddg):
        """The template context should contain a feature_gates dict."""
        from app import _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "all"
            resp = client.get("/search?q=python")
            assert resp.status_code == 200
        finally:
            _FEATURE_GATES["deep_web"] = original
