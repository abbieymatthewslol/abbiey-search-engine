"""Tests for product-knowledge fallbacks and intent helpers used by /api/chatbot-chat."""

from abbiey_product_knowledge import product_chatbot_fallback_reply


def test_voice_intent_excludes_substring_false_positives():
    r = product_chatbot_fallback_reply("check atomic number", [])
    assert "Voice / mic" not in r


def test_mic_word_boundary():
    r = product_chatbot_fallback_reply("how do I use the mic for search", [])
    assert "Voice / mic" in r
    assert "microphone" in r.lower() or "mic" in r.lower()


def test_reorder_mentions_grip():
    r = product_chatbot_fallback_reply("drag the grip to reorder my results", [])
    assert "Reordering" in r or "reorder" in r.lower()
    assert "grip" in r.lower() or "drag" in r.lower()


def test_escalation_after_generic_primer():
    first = product_chatbot_fallback_reply("asdfg vague", [])
    last_asst = {
        "role": "assistant",
        "content": "I am not sure which part of abbiey.search you mean. Try again.",
    }
    r = product_chatbot_fallback_reply("still vague", [last_asst])
    assert "I still may not" in r or "unfiltered" in r.lower()


def test_api_chatbot_fallback_on_ollama_error(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("app._ollama_chat", boom)
    r = client.post(
        "/api/chatbot-chat",
        json={"bot_id": "research", "message": "how does voice search work", "history": []},
    )
    assert r.status_code == 200
    j = r.get_json()
    assert "response" in j
    assert j.get("source") == "product_fallback"
    assert "mic" in j["response"].lower() or "voice" in j["response"].lower()
