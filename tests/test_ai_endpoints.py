"""Tests for Ollama-backed AI endpoints: /api/ai-summary and /api/chat."""

import pytest
from unittest.mock import patch, MagicMock


def test_ai_summary_returns_string(client, mock_ddg):
    with patch("app._ollama_chat", return_value="Test AI summary answer [1]."):
        resp = client.get("/api/ai-summary?q=what+is+a+test+query")
        assert resp.status_code == 200
        data = resp.get_json()
        value = (
            data.get("summary")
            or data.get("answer")
            or data.get("result")
            or list(data.values())[0]
        )
        assert isinstance(value, str)


def test_ai_summary_includes_sources(client, mock_ddg):
    with patch("app._ollama_chat", return_value="AI answer [1]."):
        resp = client.get("/api/ai-summary?q=what+is+python")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sources" in data
        assert isinstance(data["sources"], list)


def test_ai_summary_fallback_on_ollama_failure(client, mock_ddg):
    """When Ollama is down the extractive fallback must still return 200."""
    with patch("app._ollama_chat", side_effect=RuntimeError("Ollama unavailable")):
        resp = client.get("/api/ai-summary?q=how+does+gravity+work")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data


def test_chat_returns_response(client, mock_ddg):
    with patch("app._ollama_chat", return_value="Test chat answer."):
        resp = client.post("/api/chat", json={"query": "test", "message": "what is it?"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "response" in data
        assert isinstance(data["response"], str)


def test_chat_missing_fields(client):
    resp = client.post("/api/chat", json={"query": "test"})
    assert resp.status_code == 400


def test_chat_fallback_on_ollama_failure(client, mock_ddg):
    """When Ollama is down the extractive fallback must still return 200."""
    with patch("app._ollama_chat", side_effect=RuntimeError("Ollama unavailable")):
        resp = client.post("/api/chat", json={"query": "python", "message": "explain it"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "response" in data
