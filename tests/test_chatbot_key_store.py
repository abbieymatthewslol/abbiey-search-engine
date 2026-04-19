"""Tests for encrypted chatbot key persistence and resolution."""

from unittest.mock import patch


def test_chatbot_key_encrypts_and_decrypts_roundtrip(monkeypatch):
    monkeypatch.setenv("CHATBOT_KEYS_MASTER_KEY", "pytest-master-key")
    import app as app_module

    app_module._CHATBOT_KEY_FERNET = None
    app_module._CHATBOT_KEY_FERNET_SEED = ""

    token = app_module._encrypt_chatbot_secret("sk-test-secret-value")
    assert token and token != "sk-test-secret-value"
    plain = app_module._decrypt_chatbot_secret(token)
    assert plain == "sk-test-secret-value"


def test_openai_chat_config_resolves_from_encrypted_store(monkeypatch):
    monkeypatch.setenv("CHATBOT_KEYS_MASTER_KEY", "pytest-master-key")
    import app as app_module

    app_module._CHATBOT_KEY_FERNET = None
    app_module._CHATBOT_KEY_FERNET_SEED = ""
    app_module._OPENAI_KEY_BOOTSTRAPPED = False

    # Keep DB bootstrapping path deterministic for this unit test.
    with patch.object(app_module, "_bootstrap_openai_chatbot_keys_from_env", return_value=None), patch.object(
        app_module, "_fetch_decrypted_chatbot_key", side_effect=lambda slot: "sk-from-store" if slot == "research_chat" else ""
    ):
        cfg = app_module._resolve_openai_chat_config("research_chat")
    assert cfg is not None
    assert cfg["api_key"] == "sk-from-store"
    assert cfg["base_url"].startswith("http")
    assert cfg["model"]
