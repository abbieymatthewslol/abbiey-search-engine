"""Tests for GET and DELETE /api/user/history endpoints."""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth(uid=99):
    """Patch _api_auth_user to return a given uid (no bearer error)."""
    return patch("app._api_auth_user", return_value=(uid, None))


def _no_auth():
    """Patch _api_auth_user to simulate anonymous (no uid, no error)."""
    return patch("app._api_auth_user", return_value=(None, None))


# ---------------------------------------------------------------------------
# GET /api/user/history
# ---------------------------------------------------------------------------

class TestHistoryGet:
    def test_returns_401_when_anonymous(self, client):
        with _no_auth():
            resp = client.get("/api/user/history")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["history"] == []

    def test_returns_history_for_logged_in_user(self, client):
        rows = [
            {"query": "python async", "search_type": "text", "searched_at": "2026-04-07T10:00:00"},
            {"query": "flask testing", "search_type": "text", "searched_at": "2026-04-07T09:00:00"},
        ]
        with _auth(), patch("app._users_execute", return_value=rows):
            resp = client.get("/api/user/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["history"]) == 2
        assert data["history"][0]["query"] == "python async"
        assert data["history"][0]["type"] == "text"
        assert "at" in data["history"][0]

    def test_deduplicates_repeated_queries(self, client):
        rows = [
            {"query": "repeated query", "search_type": "text", "searched_at": "2026-04-07T10:00:00"},
            {"query": "other query",    "search_type": "news", "searched_at": "2026-04-07T09:30:00"},
            {"query": "repeated query", "search_type": "text", "searched_at": "2026-04-07T09:00:00"},
        ]
        with _auth(), patch("app._users_execute", return_value=rows):
            resp = client.get("/api/user/history")
        data = resp.get_json()
        queries = [h["query"] for h in data["history"]]
        assert queries.count("repeated query") == 1
        assert len(queries) == 2

    def test_caps_at_50_unique_items(self, client):
        rows = [
            {"query": f"query {i}", "search_type": "text", "searched_at": "2026-04-07T10:00:00"}
            for i in range(200)
        ]
        with _auth(), patch("app._users_execute", return_value=rows):
            resp = client.get("/api/user/history")
        data = resp.get_json()
        assert len(data["history"]) == 50

    def test_returns_empty_list_when_no_history(self, client):
        with _auth(), patch("app._users_execute", return_value=[]):
            resp = client.get("/api/user/history")
        assert resp.status_code == 200
        assert resp.get_json()["history"] == []

    def test_returns_503_on_db_error(self, client):
        with _auth(), patch("app._users_execute", side_effect=Exception("db down")):
            resp = client.get("/api/user/history")
        assert resp.status_code == 503
        assert resp.get_json()["history"] == []

    def test_defaults_search_type_to_text(self, client):
        rows = [{"query": "some query", "search_type": None, "searched_at": "2026-04-07T10:00:00"}]
        with _auth(), patch("app._users_execute", return_value=rows):
            resp = client.get("/api/user/history")
        data = resp.get_json()
        assert data["history"][0]["type"] == "text"


# ---------------------------------------------------------------------------
# DELETE /api/user/history
# ---------------------------------------------------------------------------

class TestHistoryDelete:
    def test_returns_401_when_anonymous(self, client):
        with _no_auth():
            resp = client.delete("/api/user/history", json={"query": "test"})
        assert resp.status_code == 401

    def test_deletes_specific_query(self, client):
        with _auth(), patch("app._users_execute", return_value=None) as mock_db:
            resp = client.delete("/api/user/history", json={"query": "python async"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        call_args = mock_db.call_args[0]
        assert "DELETE" in call_args[0]
        assert "python async" in call_args[1]

    def test_clear_all_deletes_all_rows(self, client):
        with _auth(), patch("app._users_execute", return_value=None) as mock_db:
            resp = client.delete("/api/user/history", json={"clear_all": True})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["cleared"] is True
        call_sql = mock_db.call_args[0][0]
        assert "user_id" in call_sql
        assert "query" not in call_sql  # clear_all doesn't filter by query

    def test_returns_400_when_no_query_and_no_clear_all(self, client):
        with _auth():
            resp = client.delete("/api/user/history", json={})
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_returns_400_when_empty_query_string(self, client):
        with _auth():
            resp = client.delete("/api/user/history", json={"query": "   "})
        assert resp.status_code == 400

    def test_returns_503_on_db_error_single_delete(self, client):
        with _auth(), patch("app._users_execute", side_effect=Exception("db down")):
            resp = client.delete("/api/user/history", json={"query": "failing query"})
        assert resp.status_code == 503

    def test_returns_503_on_db_error_clear_all(self, client):
        with _auth(), patch("app._users_execute", side_effect=Exception("db down")):
            resp = client.delete("/api/user/history", json={"clear_all": True})
        assert resp.status_code == 503

    def test_truncates_long_query_to_500_chars(self, client):
        long_q = "x" * 600
        with _auth(), patch("app._users_execute", return_value=None) as mock_db:
            resp = client.delete("/api/user/history", json={"query": long_q})
        assert resp.status_code == 200
        passed_q = mock_db.call_args[0][1][1]
        assert len(passed_q) == 500
