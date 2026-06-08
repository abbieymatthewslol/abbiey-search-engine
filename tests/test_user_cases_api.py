"""Tests for investigation cases and dashboard APIs."""

from __future__ import annotations

import uuid

from werkzeug.security import generate_password_hash

import app as app_module


def _login_test_user(client, prefix: str = "case") -> int:
    suffix = uuid.uuid4().hex[:10]
    rows = app_module._users_execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
        [f"{prefix}_{suffix}", f"{prefix}_{suffix}@example.com", generate_password_hash("password123")],
        return_id=True,
    )
    uid = rows[0]["id"]
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return uid


class TestUserCasesApi:
    def test_cases_require_auth(self, client):
        resp = client.get("/api/user/cases")
        assert resp.status_code == 401

    def test_create_list_update_add_item_and_delete_case(self, client):
        uid = _login_test_user(client, "cases")

        create_resp = client.post(
            "/api/user/cases",
            json={
                "title": "John Smith",
                "summary": "Initial lead set",
                "notes": "Track aliases and social accounts",
                "last_query": "john smith melbourne",
                "item": {
                    "item_type": "search",
                    "section": "queries",
                    "label": "john smith melbourne",
                    "url": "/search?q=john+smith+melbourne",
                    "meta": {"type": "people"},
                },
            },
        )
        assert create_resp.status_code == 201
        case_id = create_resp.get_json()["id"]
        assert case_id

        list_resp = client.get("/api/user/cases?details=1")
        assert list_resp.status_code == 200
        cases = list_resp.get_json()["cases"]
        assert len(cases) >= 1
        case = next(c for c in cases if c["id"] == case_id)
        assert case["title"] == "John Smith"
        assert case["item_count"] == 1
        assert len(case["items"]) == 1
        assert case["items"][0]["meta"]["type"] == "people"

        update_resp = client.post(
            f"/api/user/cases/{case_id}",
            json={
                "title": "John Smith Case",
                "summary": "Expanded lead set",
                "notes": "Added employer angle",
                "last_query": "john smith linkedin",
            },
        )
        assert update_resp.status_code == 200
        assert update_resp.get_json()["ok"] is True

        item_resp = client.post(
            f"/api/user/cases/{case_id}/items",
            json={
                "item_type": "result",
                "section": "profiles",
                "label": "LinkedIn profile",
                "url": "https://example.com/linkedin",
                "meta": {"source": "manual"},
            },
        )
        assert item_resp.status_code == 201

        rows = app_module._users_execute(
            "SELECT title, summary, notes, last_query FROM user_cases WHERE id=? AND user_id=?",
            [case_id, uid],
        )
        assert rows
        assert rows[0]["title"] == "John Smith Case"
        assert rows[0]["last_query"] == "john smith linkedin"

        item_rows = app_module._users_execute(
            "SELECT COUNT(*) AS cnt FROM user_case_items WHERE case_id=?",
            [case_id],
        )
        assert int(item_rows[0]["cnt"]) == 2

        delete_resp = client.delete(f"/api/user/cases/{case_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.get_json()["ok"] is True

        deleted_rows = app_module._users_execute(
            "SELECT id FROM user_cases WHERE id=? AND user_id=?",
            [case_id, uid],
        )
        assert deleted_rows == []

    def test_dashboard_returns_case_counts_and_recent_activity(self, client):
        uid = _login_test_user(client, "dash")

        case_rows = app_module._users_execute(
            "INSERT INTO user_cases (user_id, title, summary, last_query, updated_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
            [uid, "Acme Review", "Supplier lookups", "acme pty ltd"],
            return_id=True,
        )
        case_id = case_rows[0]["id"]
        app_module._users_execute(
            "INSERT INTO user_case_items (case_id, item_type, section, label, url, meta_json) VALUES (?,?,?,?,?,?)",
            [case_id, "search", "queries", "acme pty ltd", "/search?q=acme+pty+ltd", '{"type":"business"}'],
        )
        app_module._users_execute(
            "INSERT INTO user_bookmarks (user_id, url, title, snippet) VALUES (?,?,?,?)",
            [uid, "https://example.com/acme", "Acme", "Bookmark"],
        )
        app_module._users_execute(
            "INSERT INTO user_search_history (user_id, query, search_type) VALUES (?,?,?)",
            [uid, "acme pty ltd", "text"],
        )

        resp = client.get("/api/user/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["counts"]["cases"] >= 1
        assert data["counts"]["bookmarks"] >= 1
        assert data["counts"]["history"] >= 1
        assert any(case["id"] == case_id for case in data["cases"])
        assert any(item["query"] == "acme pty ltd" for item in data["recent_searches"])
        assert any(item["url"] == "https://example.com/acme" for item in data["recent_bookmarks"])
        assert "focus_modes" in data
        assert "entity_hints" in data
        assert "stats" in data
        assert "activity_score" in data
        assert data["user"]["username"]

    def test_cannot_modify_other_users_case(self, client):
        owner_id = _login_test_user(client, "owner")
        case_rows = app_module._users_execute(
            "INSERT INTO user_cases (user_id, title, updated_at) VALUES (?,?,CURRENT_TIMESTAMP)",
            [owner_id, "Private Case"],
            return_id=True,
        )
        case_id = case_rows[0]["id"]

        other_client = client.application.test_client()
        _login_test_user(other_client, "intruder")

        update_resp = other_client.post(
            f"/api/user/cases/{case_id}",
            json={"title": "Hijacked", "summary": "", "notes": "", "last_query": ""},
        )
        assert update_resp.status_code == 404

        item_resp = other_client.post(
            f"/api/user/cases/{case_id}/items",
            json={"label": "Nope", "url": "https://example.com"},
        )
        assert item_resp.status_code == 404

        delete_resp = other_client.delete(f"/api/user/cases/{case_id}")
        assert delete_resp.status_code == 404
