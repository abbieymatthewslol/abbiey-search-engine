"""Tests for optional LLM result reordering."""

from retrieval.llm_rerank import rerank_text_hits_with_llm


def test_rerank_swaps_order_when_model_returns_permutation():
    hits = [
        {"title": "B second", "url": "https://b.test", "body": "bee"},
        {"title": "A first", "url": "https://a.test", "body": "ay"},
    ]

    def _chat(_messages, timeout=10.0):
        return "[2, 1]"

    out = rerank_text_hits_with_llm("test q", hits, chat_fn=_chat)
    assert out[0]["url"] == "https://a.test"
    assert out[1]["url"] == "https://b.test"


def test_rerank_falls_back_on_bad_json():
    hits = [
        {"title": "One", "url": "https://1.test", "body": "x"},
        {"title": "Two", "url": "https://2.test", "body": "y"},
    ]

    def _bad(_messages, timeout=10.0):
        return "not json"

    assert rerank_text_hits_with_llm("q", hits, chat_fn=_bad) == hits
