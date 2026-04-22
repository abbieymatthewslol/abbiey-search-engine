"""Smoke tests for /api/onion-check and /admin/api/stream.

Covers the three previously-broken code paths repaired by the bug-fix PR:
- `_check_single_onion` (uses `resp.status_code` after httpx call)
- `/api/onion-check` route that dispatches to `_check_single_onion`
- `/admin/api/stream` SSE route that relies on the `queue` stdlib module
"""

from unittest.mock import MagicMock, patch

import pytest

import app as app_module


# ---------------------------------------------------------------------------
# /api/onion-check
# ---------------------------------------------------------------------------


class TestApiOnionCheck:
    """Thin smoke coverage for the onion link verification endpoint."""

    def setup_method(self):
        # Cached results would short-circuit the mocked httpx call, so clear it.
        with app_module._onion_status_lock:
            app_module._onion_status_cache.clear()

    def test_rejects_non_list_payload(self, client):
        resp = client.post("/api/onion-check", json={"urls": "not-a-list"})
        assert resp.status_code == 400
        assert resp.get_json()["error"]

    def test_rejects_empty_list(self, client):
        resp = client.post("/api/onion-check", json={"urls": []})
        assert resp.status_code == 400

    def test_skips_non_onion_hostnames_as_down(self, client):
        """Hostnames that don't match the onion pattern are marked 'down' without
        hitting httpx/Tor."""
        resp = client.post(
            "/api/onion-check",
            json={"urls": ["http://example.com/foo"]},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["results"]["http://example.com/foo"] == "down"

    def test_marks_reachable_onion_as_live(self, client):
        """_check_single_onion should parse resp.status_code correctly after the
        fix — status < 400 → 'live'. Regression guard for F821 undefined 'resp'.
        """
        onion_url = "http://abcdefghijklmnop.onion/"

        fake_resp = MagicMock()
        fake_resp.status_code = 200

        fake_client = MagicMock()
        fake_client.__enter__.return_value = fake_client
        fake_client.__exit__.return_value = False
        fake_client.head.return_value = fake_resp

        with patch.object(app_module.httpx, "Client", return_value=fake_client), \
             patch.object(app_module.httpx, "HTTPTransport", return_value=MagicMock()):
            resp = client.post("/api/onion-check", json={"urls": [onion_url]})

        assert resp.status_code == 200
        assert resp.get_json()["results"][onion_url] == "live"

    def test_marks_unreachable_onion_as_unknown(self, client):
        """If the Tor proxy raises, status is reported as 'unknown' (not cached)."""
        onion_url = "http://zyxwvutsrqponmlk.onion/"

        def _boom(*_args, **_kwargs):
            raise RuntimeError("tor not running")

        with patch.object(app_module.httpx, "HTTPTransport", side_effect=_boom):
            resp = client.post("/api/onion-check", json={"urls": [onion_url]})

        assert resp.status_code == 200
        assert resp.get_json()["results"][onion_url] == "unknown"


# ---------------------------------------------------------------------------
# /admin/api/stream
# ---------------------------------------------------------------------------


class TestAdminApiStream:
    """Smoke coverage for the SSE admin stream — verifies the `queue` import works."""

    def test_rejects_without_admin_token(self, client):
        """Without ADMIN_TOKEN configured, admin routes must return 403."""
        with patch.object(app_module, "_ADMIN_TOKEN", ""):
            resp = client.get("/admin/api/stream")
        assert resp.status_code == 403

    def test_rejects_bad_token(self, client):
        with patch.object(app_module, "_ADMIN_TOKEN", "correct-token"):
            resp = client.get("/admin/api/stream?token=wrong")
        assert resp.status_code == 403

    def test_authorised_stream_opens_and_sends_connected_event(self, client):
        """Authorised request must return a streaming text/event-stream response
        with an initial 'connected' event. Regression guard for missing `import
        queue` — the route would otherwise NameError at runtime.
        """
        with patch.object(app_module, "_ADMIN_TOKEN", "smoke-token"):
            resp = client.get(
                "/admin/api/stream?token=smoke-token",
                buffered=False,
            )
            assert resp.status_code == 200
            assert resp.mimetype == "text/event-stream"
            # Pull the first SSE frame off the generator; that proves the
            # client_q: queue.Queue(...) construction succeeded.
            first_chunk = next(resp.response)
            resp.close()

        assert b"event: connected" in first_chunk
        assert b"\"status\":\"ok\"" in first_chunk
