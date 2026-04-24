"""Unit tests for ``services.search_aggregator`` (no live HTTP)."""

from services.search_aggregator import (
    _intent_mul,
    _normalize_agg_url,
    _to_hits,
    clear_aggregator_cache,
    search_ddg,
)


def test_normalize_agg_url_strips_utm():
    a = _normalize_agg_url("https://Example.com/path/?utm_source=x&id=1")
    b = _normalize_agg_url("https://example.com/path?id=1")
    assert a == b


def test_search_ddg_uses_injected_fetcher():
    rows = search_ddg(
        "ignored",
        ddg_fetcher=lambda: [{"title": "T", "href": "https://a.org/x", "body": "snippet"}],
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "ddg"
    assert rows[0]["url"] == "https://a.org/x"
    assert rows[0]["snippet"] == "snippet"


def test_intent_boosts():
    assert _intent_mul("what is gravity")["wikipedia"] > 1.0
    assert _intent_mul("latest news")["reddit"] > 1.0
    assert _intent_mul("buy cheap shoes")["brave"] > 1.0


def test_to_hits_flask_shape():
    hits = _to_hits(
        [
            {
                "title": "Hi",
                "url": "https://en.wikipedia.org/wiki/X",
                "snippet": "S",
                "source": "wikipedia",
                "score": 2.0,
                "timestamp": "2026-01-01",
            }
        ]
    )
    assert hits[0]["body"] == "S"
    assert hits[0]["url"].endswith("wiki/X")
    assert hits[0]["date"] == "2026-01-01"


def test_clear_aggregator_cache_no_crash():
    clear_aggregator_cache()
