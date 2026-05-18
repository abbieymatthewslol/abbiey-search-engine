"""Tests for research assistant images and saved chats."""

import base64
import json

import pytest

import research_chat as rc


def test_parse_chat_image_data_url():
    raw = b"\xff\xd8\xff\xe0" + b"x" * 40
    b64 = base64.b64encode(raw).decode()
    url = f"data:image/jpeg;base64,{b64}"
    payload, mime = rc.parse_chat_image(url)
    assert payload == b64
    assert mime == "image/jpeg"


def test_parse_chat_image_rejects_large():
    raw = b"\x89PNG\r\n" + (b"x" * (rc.MAX_CHAT_IMAGE_BYTES + 1))
    b64 = base64.b64encode(raw).decode()
    url = f"data:image/png;base64,{b64}"
    payload, err = rc.parse_chat_image(url)
    assert payload is None
    assert "too large" in err.lower()


def test_build_ollama_messages_includes_image():
    messages = rc.build_ollama_messages(
        query="cats",
        context="Search results for 'cats':\n1. Cat wiki",
        history=[],
        message="What breed is this?",
        image_b64="abc123",
        image_mime="image/jpeg",
    )
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assert user_msgs
    assert user_msgs[-1].get("images") == ["abc123"]


def test_normalize_history_with_image():
    history = [{"role": "user", "content": "look", "image": "data:image/png;base64,abcd"}]
    out, err = rc.normalize_history(history, max_turns=12, max_message_len=1000)
    assert err is None
    assert out[0]["image"].startswith("data:image/png")


class TestResearchChatAPI:
    def test_chat_image_only_requires_valid_image(self, client, mock_ddg, mock_chat):
        resp = client.post("/api/chat", json={
            "query": "test",
            "message": "",
            "image": "not-an-image",
            "history": [],
        })
        assert resp.status_code == 400

    def test_chat_with_image(self, client, mock_ddg, mock_chat):
        raw = b"\xff\xd8\xff\xe0" + b"x" * 40
        b64 = base64.b64encode(raw).decode()
        resp = client.post("/api/chat", json={
            "query": "test",
            "message": "Describe this image",
            "image": f"data:image/jpeg;base64,{b64}",
            "history": [],
        })
        assert resp.status_code == 200
        assert mock_chat.called
        call_messages = mock_chat.call_args[0][0]
        assert any(m.get("images") for m in call_messages if isinstance(m, dict))

    def test_research_chats_guest_list(self, client):
        resp = client.get("/api/research-chats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["authenticated"] is False
        assert data["chats"] == []

    def test_research_chats_save_requires_auth(self, client):
        resp = client.post("/api/research-chats", json={
            "query": "python",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert resp.status_code == 401

    def test_research_chats_save_and_list(self, client, monkeypatch):
        with client.session_transaction() as sess:
            sess["user_id"] = 1
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "A programming language."},
        ]
        monkeypatch.setattr(
            "app._research_chat.save_chat",
            lambda uid, execute_fn, **kw: {"id": 42, "title": "What is Python?"},
        )
        monkeypatch.setattr(
            "app._research_chat.list_saved_chats",
            lambda uid, execute_fn, search_query="": [{
                "id": 42,
                "query": "python",
                "title": "What is Python?",
                "message_count": 2,
            }],
        )
        save = client.post("/api/research-chats", json={
            "query": "python",
            "messages": messages,
        })
        assert save.status_code == 200
        assert save.get_json()["id"] == 42
        listing = client.get("/api/research-chats?query=python")
        assert listing.status_code == 200
        chats = listing.get_json()["chats"]
        assert len(chats) == 1
        assert chats[0]["title"] == "What is Python?"
