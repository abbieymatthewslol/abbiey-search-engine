"""Tests for /admin/api/chat chatbot routing and fallbacks."""

from unittest.mock import patch


def _admin_headers(monkeypatch):
    monkeypatch.setattr("app._ADMIN_TOKEN", "test-admin-token")
    return {"X-Admin-Token": "test-admin-token"}


def test_admin_chat_requires_token(client):
    resp = client.post("/admin/api/chat", json={"message": "hello"})
    assert resp.status_code == 403


def test_admin_chat_uses_ollama_first(client, monkeypatch):
    headers = _admin_headers(monkeypatch)
    with patch("app._ollama_chat", return_value="ollama reply"), patch("app._openai_chat") as openai_mock:
        resp = client.post("/admin/api/chat", json={"message": "hello"}, headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["source"] == "ollama"
        assert data["reply"] == "ollama reply"
        assert not openai_mock.called


def test_admin_chat_uses_openai_when_ollama_fails(client, monkeypatch):
    headers = _admin_headers(monkeypatch)
    with patch("app._ollama_chat", side_effect=RuntimeError("down")), patch(
        "app._openai_chat", return_value="openai reply"
    ) as openai_mock:
        resp = client.post("/admin/api/chat", json={"message": "hello"}, headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["source"] == "openai"
        assert data["reply"] == "openai reply"
        openai_mock.assert_called_once()
        args, kwargs = openai_mock.call_args
        assert kwargs["chatbot"] == "admin_chat"


def test_admin_chat_falls_back_to_builtin(client, monkeypatch):
    headers = _admin_headers(monkeypatch)
    with patch("app._ollama_chat", side_effect=RuntimeError("down")), patch(
        "app._openai_chat", side_effect=RuntimeError("down")
    ), patch("app._abbiey_bot_fallback", return_value="builtin reply"):
        resp = client.post("/admin/api/chat", json={"message": "hello"}, headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["source"] == "builtin"
        assert data["reply"] == "builtin reply"
