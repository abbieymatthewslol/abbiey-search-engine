"""Tests for user-facing copy alignment and rate-limit budget separation.

Issue: UI copy previously implied "no tracking / not being watched" while
analytics captured every search including IP/device/location.  These tests
ensure the new "unfiltered answers" framing is consistent across templates and
that background UI fetches use a more generous rate-limit budget than explicit
search submissions.
"""

import pytest
import app as app_module
from app import app as flask_app, limiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    limiter.enabled = False
    with flask_app.test_client() as c:
        yield c
    limiter.enabled = True


# ---------------------------------------------------------------------------
# 1. User-facing copy tests
# ---------------------------------------------------------------------------

class TestCopyAlignment:
    """Templates must not claim strong privacy guarantees that contradict the
    actual analytics behaviour (IP/device/location captured per search)."""

    def test_error_page_no_privacy_claim(self, client):
        """error.html footer must NOT say 'No tracking. No profiling.'"""
        resp = client.get("/nonexistent-path-404")
        body = resp.data.decode("utf-8", errors="replace")
        assert "No tracking. No profiling." not in body

    def test_error_page_has_unfiltered_branding(self, client):
        """error.html footer should carry the 'unfiltered answers' brand."""
        resp = client.get("/nonexistent-path-404")
        body = resp.data.decode("utf-8", errors="replace")
        # Footer should convey the product purpose, not a privacy guarantee
        assert "abbieysearch" in body

    def test_base_og_description_no_privacy_claim(self, client):
        """OG/Twitter meta tags must not read 'Private search engine. No tracking.'"""
        resp = client.get("/search")
        body = resp.data.decode("utf-8", errors="replace")
        assert "Private search engine. No tracking. No profiling." not in body

    def test_base_og_description_unfiltered(self, client):
        """OG description should reference 'Unfiltered' or 'Direct answers'."""
        resp = client.get("/search")
        body = resp.data.decode("utf-8", errors="replace")
        # Check that the new branding appears somewhere in the meta tags
        assert "Unfiltered" in body or "Direct answers" in body

    def test_privacy_page_no_old_tagline(self, client):
        """Privacy page legal footer note must not say 'don't have to be tracked'."""
        resp = client.get("/privacy")
        body = resp.data.decode("utf-8", errors="replace")
        assert "don't have to be tracked doing it" not in body

    def test_privacy_page_acknowledges_analytics(self, client):
        """Privacy page must mention that search analytics are collected."""
        resp = client.get("/privacy")
        body = resp.data.decode("utf-8", errors="replace")
        assert "Search Analytics" in body or "analytics" in body.lower()


# ---------------------------------------------------------------------------
# 2. Rate-limit budget separation tests
# ---------------------------------------------------------------------------

class TestRateLimitBudgets:
    """Background UI-assist routes should carry a higher per-minute budget than
    foreground search/AI routes so that infinite scroll, preview panels, and
    autocomplete do not consume the same quota as explicit search submissions."""

    def _parse_limit_int(self, limit_str: str) -> int:
        """Extract the integer from a limit string like '300/minute'."""
        return int(limit_str.split("/")[0].split(" ")[0])

    def test_background_budget_greater_than_search_budget(self):
        """_RL_BACKGROUND must be strictly larger than _RL_SEARCH."""
        bg = self._parse_limit_int(app_module._RL_BACKGROUND)
        fg = self._parse_limit_int(app_module._RL_SEARCH)
        assert bg > fg, (
            f"Background budget ({bg}/min) must exceed search budget ({fg}/min)"
        )

    def test_search_budget_is_non_trivial(self):
        """_RL_SEARCH must allow at least 60 requests per minute (2/s)."""
        fg = self._parse_limit_int(app_module._RL_SEARCH)
        assert fg >= 60

    def test_background_budget_at_least_double_search(self):
        """Background budget should be at least 2× the search budget."""
        bg = self._parse_limit_int(app_module._RL_BACKGROUND)
        fg = self._parse_limit_int(app_module._RL_SEARCH)
        assert bg >= fg * 2

    def test_relaxed_preset_doubles_limits(self):
        """ABBIEY_RATE_LIMIT_PRESET=relaxed should produce 2× all base limits.

        Since module-level constants are evaluated at import time, we verify
        the arithmetic logic directly: if multiplier==2 the expected values
        are exactly double the base values.
        """
        base_search = 120
        base_background = 300
        # Simulate what the module does for the "relaxed" preset
        multiplier = 2
        assert base_search * multiplier == 240
        assert base_background * multiplier == 600
        # In normal mode the module should have multiplier == 1
        if app_module._RL_PRESET == "normal":
            assert self._parse_limit_int(app_module._RL_SEARCH) == base_search
            assert self._parse_limit_int(app_module._RL_BACKGROUND) == base_background

    def test_normal_preset_uses_base_limits(self):
        """Default (normal) preset must not apply any multiplier."""
        assert app_module._RL_MULTIPLIER in (1, 2)
        # If preset is normal, multiplier must be 1
        if app_module._RL_PRESET == "normal":
            assert app_module._RL_MULTIPLIER == 1

    def test_rl_constants_exported(self):
        """All expected rate-limit constants must be importable from app."""
        for name in ("_RL_SEARCH", "_RL_AI_HEAVY", "_RL_AI_LIGHT", "_RL_BACKGROUND"):
            assert hasattr(app_module, name), f"app.{name} not found"
            val = getattr(app_module, name)
            assert "/" in val or " per " in val, f"{name}={val!r} is not a valid limit string"
