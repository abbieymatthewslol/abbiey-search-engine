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


def test_chatbot_secret_encrypt_decrypt_roundtrip():
    import app as app_module

    raw = "sk-proj-test-secret-12345"
    token = app_module._encrypt_chatbot_secret(raw)
    assert token
    assert token != raw
    assert app_module._decrypt_chatbot_secret(token) == raw


def test_chatbot_secret_persistence_roundtrip(monkeypatch):
    import app as app_module

    app_module._OPENAI_KEY_BOOTSTRAPPED = False
    app_module._upsert_encrypted_chatbot_key(
        "research_chat",
        "sk-proj-persist-research-0001",
        source_env="pytest",
    )
    app_module._upsert_encrypted_chatbot_key(
        "admin_chat",
        "sk-proj-persist-admin-0002",
        source_env="pytest",
    )
    app_module._OPENAI_KEY_BOOTSTRAPPED = True

    cfg_research = app_module._resolve_openai_chat_config("research_chat")
    cfg_admin = app_module._resolve_openai_chat_config("admin_chat")
    assert cfg_research is not None
    assert cfg_admin is not None
    assert cfg_research["api_key"] == "sk-proj-persist-research-0001"
    assert cfg_admin["api_key"] == "sk-proj-persist-admin-0002"


def test_chatbot_secret_bootstrap_from_env(monkeypatch):
    import app as app_module

    monkeypatch.setenv("OPENAI_API_KEY_RESEARCH_CHAT", "sk-proj-env-research-0099")
    monkeypatch.delenv("OPENAI_API_KEY_ADMIN_CHAT", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_CHAT", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app_module._OPENAI_KEY_BOOTSTRAPPED = False

    cfg = app_module._resolve_openai_chat_config("research_chat")
    assert cfg is not None
    assert cfg["api_key"] == "sk-proj-env-research-0099"
