"""Tests for retrieval.open_catalog_blend (Wikidata / OpenAlex / Crossref blend)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from retrieval.open_catalog_blend import (
    _openalex_blurb,
    fetch_open_knowledge_hits,
    _wikidata_hits,
)


def test_openalex_blurb_reconstructs_order():
    inv = {"Hello": [0], "world": [1]}
    assert _openalex_blurb(inv) == "Hello world"


def test_wikidata_hits_parses_search_and_sitelinks():
    calls = []

    def fake_get(url, params=None, headers=None, timeout=5.0):
        calls.append((url, dict(params or {})))
        mock = MagicMock()
        mock.status_code = 200
        if params and params.get("action") == "wbsearchentities":
            mock.json.return_value = {
                "search": [
                    {"id": "Q42", "label": "Douglas Adams", "description": "Author"},
                ]
            }
        elif params and params.get("action") == "wbgetentities":
            mock.json.return_value = {
                "entities": {
                    "Q42": {
                        "sitelinks": {
                            "enwiki": {"title": "Douglas Adams"},
                        }
                    }
                }
            }
        else:
            mock.json.return_value = {}
        return mock

    with patch("retrieval.open_catalog_blend._http_get", side_effect=fake_get):
        hits = _wikidata_hits("douglas adams", limit=3)

    assert len(hits) == 1
    assert hits[0]["title"] == "Douglas Adams"
    assert "wikipedia.org/wiki/Douglas_Adams" in hits[0]["url"]
    assert any(p.get("action") == "wbsearchentities" for _, p in calls)


def test_fetch_open_knowledge_hits_dedupes_urls():
    wd = [{"title": "A", "url": "https://example.com/a", "body": "x", "source": "Wikidata"}]
    oa = [{"title": "A2", "url": "https://example.com/a", "body": "y", "source": "OpenAlex"}]
    cr = [{"title": "B", "url": "https://doi.org/10.1234/x", "body": "z", "source": "Crossref"}]

    with (
        patch("retrieval.open_catalog_blend._wikidata_hits", return_value=wd),
        patch("retrieval.open_catalog_blend._openalex_hits", return_value=oa),
        patch("retrieval.open_catalog_blend._crossref_lite_hits", return_value=cr),
    ):
        out = fetch_open_knowledge_hits("test query", max_total=10)

    urls = [h["url"] for h in out]
    assert urls.count("https://example.com/a") == 1
    assert "https://doi.org/10.1234/x" in urls


def test_fetch_empty_query():
    assert fetch_open_knowledge_hits("   ") == []
