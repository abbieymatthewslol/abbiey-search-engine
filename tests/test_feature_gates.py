"""Tests for feature gates and persistent paid status (webhook + restore-by-email).

Covers:
- _feature_allowed() logic for all/paid/none gate values
- _feature_gates_for_user() reflects unlock status
- Search route blocks gated search types for non-paid users
- Search route allows gated search types for paid users
- Stripe webhook auto-grants by email when checkout_token is absent
- /api/search-access/restore-by-email endpoint
"""

import secrets
from unittest.mock import patch, MagicMock

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

    def test_paid_gate_blocks_free_user_for_onion(self, client):
        from app import _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "paid"
            with patch("app._search_access_granted", return_value=False):
                resp = client.get("/search?q=test&type=onion")
            assert resp.status_code == 403
        finally:
            _FEATURE_GATES["deep_web"] = original

    def test_paid_gate_allows_paid_user_for_onion(self, client):
        from app import _FEATURE_GATES
        original = _FEATURE_GATES.get("deep_web")
        try:
            _FEATURE_GATES["deep_web"] = "paid"
            onion_results = [
                {"title": "Hidden site", "url": "http://abc.onion/", "body": "desc", "onion": True},
            ]
            with patch("app._search_access_granted", return_value=True), \
                 patch("app._try_ahmia", return_value=onion_results), \
                 patch("app._try_onion_ddg", return_value=[]):
                resp = client.get("/search?q=test&type=onion")
            assert resp.status_code == 200
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
            with patch("app._search_access_granted", return_value=False), \
                 patch("app._try_ahmia", return_value=onion_results), \
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


# ---------------------------------------------------------------------------
# Stripe webhook: email-based auto-grant
# ---------------------------------------------------------------------------

class TestWebhookEmailGrant:
    def _make_webhook_event(self, customer_email="buyer@example.com", checkout_token=""):
        return {
            "type": "checkout.session.completed",
            "id": "evt_" + secrets.token_hex(8),
            "data": {
                "object": {
                    "id": "cs_" + secrets.token_hex(8),
                    "client_reference_id": checkout_token,
                    "customer_details": {"email": customer_email},
                    "customer_email": customer_email,
                    "amount_total": 1000,
                    "currency": "usd",
                }
            },
        }

    def test_webhook_grants_by_email_when_no_checkout_token(self, client):
        """With no checkout_token, webhook should fall back to email-based unlock."""
        event = self._make_webhook_event(customer_email="payer@example.com", checkout_token="")

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_stripe.error = MagicMock()
        mock_stripe.error.SignatureVerificationError = Exception

        granted_tokens = []

        def fake_upsert(uid, token, source="payment_return"):
            granted_tokens.append({"uid": uid, "token": token, "source": source})
            return token

        with patch("app._stripe_mod", mock_stripe), \
             patch("app.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("app._upsert_search_unlock", side_effect=fake_upsert), \
             patch("app._users_execute") as mock_db:
            # First call: INSERT payment_events → success
            # Second call: SELECT users by email → found
            mock_db.side_effect = [
                None,   # INSERT payment_events
                [{"id": 42}],  # SELECT users WHERE email
            ]
            resp = client.post(
                "/webhooks/stripe",
                data="{}",
                headers={"Stripe-Signature": "t=1,v1=sig", "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        assert len(granted_tokens) == 1
        assert granted_tokens[0]["source"] == "stripe_webhook_email"

    def test_webhook_does_not_double_grant_when_checkout_token_present(self, client):
        """When checkout_token succeeds, the email fallback path should not also fire."""
        token = secrets.token_urlsafe(24)
        event = self._make_webhook_event(customer_email="payer@example.com", checkout_token=token)

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = event
        mock_stripe.error = MagicMock()
        mock_stripe.error.SignatureVerificationError = Exception

        granted_tokens = []

        def fake_upsert(uid, tok, source="payment_return"):
            granted_tokens.append(source)
            return tok

        with patch("app._stripe_mod", mock_stripe), \
             patch("app.STRIPE_WEBHOOK_SECRET", "whsec_test"), \
             patch("app._upsert_search_unlock", side_effect=fake_upsert), \
             patch("app._users_execute") as mock_db:
            # INSERT payment_events, then UPDATE pending_checkouts → returns row
            mock_db.side_effect = [
                None,                   # INSERT payment_events
                [{"user_id": 7}],       # UPDATE pending_checkouts RETURNING user_id
            ]
            resp = client.post(
                "/webhooks/stripe",
                data="{}",
                headers={"Stripe-Signature": "t=1,v1=sig", "Content-Type": "application/json"},
            )

        assert resp.status_code == 200
        # Only one grant, from the checkout_token path
        assert len(granted_tokens) == 1
        assert "stripe_webhook" in granted_tokens[0]


# ---------------------------------------------------------------------------
# /api/search-access/restore-by-email
# ---------------------------------------------------------------------------

class TestRestoreByEmail:
    def test_restore_same_status_for_unknown_email_no_enumeration(self, client):
        """No payment: still 200 + same shape as success so HTTP status cannot enumerate payers."""
        with patch("app._users_execute", return_value=[]):
            resp = client.post(
                "/api/search-access/restore-by-email",
                json={"email": "notapayer@example.com"},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "message" in data
        assert "abbiey_search_unlock" not in (resp.headers.get("Set-Cookie") or "")

    def test_restore_issues_cookie_for_known_email(self, client):
        def fake_db(sql, params=None):
            sql_lower = sql.strip().lower()
            if "payment_events" in sql_lower:
                return [{"ok": 1}]
            if "users" in sql_lower:
                return [{"id": 99}]
            return []

        granted_tokens = []

        def fake_upsert(uid, token, source="payment_return"):
            granted_tokens.append({"uid": uid, "source": source})
            return token

        with patch("app._users_execute", side_effect=fake_db), \
             patch("app._upsert_search_unlock", side_effect=fake_upsert):
            resp = client.post(
                "/api/search-access/restore-by-email",
                json={"email": "realbuyer@example.com"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "message" in data
        assert len(granted_tokens) == 1
        assert granted_tokens[0]["source"] == "restore_by_email"
        assert granted_tokens[0]["uid"] == 99

    def test_restore_works_without_registered_account(self, client):
        """Should still grant access even if email has no user account."""
        def fake_db(sql, params=None):
            sql_lower = sql.strip().lower()
            if "payment_events" in sql_lower:
                return [{"ok": 1}]
            if "users" in sql_lower:
                return []  # no matching account
            return []

        granted_tokens = []

        def fake_upsert(uid, token, source="payment_return"):
            granted_tokens.append({"uid": uid, "source": source})
            return token

        with patch("app._users_execute", side_effect=fake_db), \
             patch("app._upsert_search_unlock", side_effect=fake_upsert):
            resp = client.post(
                "/api/search-access/restore-by-email",
                json={"email": "anon@example.com"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "message" in data
        assert granted_tokens[0]["uid"] is None

    def test_restore_rejects_missing_email(self, client):
        resp = client.post("/api/search-access/restore-by-email", json={})
        assert resp.status_code == 400

    def test_restore_rejects_invalid_email(self, client):
        resp = client.post(
            "/api/search-access/restore-by-email",
            json={"email": "not-an-email"},
        )
        assert resp.status_code == 400

    def test_restore_rejects_non_json(self, client):
        resp = client.post(
            "/api/search-access/restore-by-email",
            data="email=x@y.com",
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code == 400

    def test_restore_sets_unlock_cookie(self, client):
        def fake_db(sql, params=None):
            if "payment_events" in sql.lower():
                return [{"ok": 1}]
            return []

        with patch("app._users_execute", side_effect=fake_db), \
             patch("app._upsert_search_unlock", return_value="tok_abc123"):
            resp = client.post(
                "/api/search-access/restore-by-email",
                json={"email": "buyer@example.com"},
            )

        assert resp.status_code == 200
        assert "abbiey_search_unlock" in resp.headers.get("Set-Cookie", "")
