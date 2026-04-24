"""Tests for retrieval aggregation, scoring, dedup, and pipeline."""

import asyncio

import pytest

from retrieval.aggregator import aggregate_sources
from retrieval.dedup import deduplicate_results, normalize_url
from retrieval.normalize import raw_dict_to_normalized
from retrieval.intent import intent_alignment_delta
from retrieval.pipeline import apply_pipeline_stages, query_time_sensitive, run_text_retrieval_pipeline_sync
from retrieval.types import NormalizedResult, RetrievalParams


def test_normalize_url_strips_utm():
    a = normalize_url("https://Example.com/path/?utm_source=x&id=1")
    b = normalize_url("https://example.com/path?id=1")
    assert a == b


def test_query_time_sensitive():
    assert query_time_sensitive("latest news today") is True
    assert query_time_sensitive("how to install python") is False


def test_raw_dict_to_normalized_maps_body():
    r = raw_dict_to_normalized(
        {"title": "T", "href": "https://a.com", "body": "snippet"},
        source="ddg",
        rank=0,
    )
    assert r is not None
    assert r.snippet == "snippet"
    assert r.domain == "a.com"


def test_dedup_drops_same_normalized_url():
    a = NormalizedResult("t", "https://x.com/?utm_source=1", "s", "src", None, "x.com", 0, {})
    b = NormalizedResult("t", "https://x.com/", "s2", "src", None, "x.com", 1, {})
    out = deduplicate_results([a, b])
    assert len(out) == 1


def test_people_search_intent_prefers_directory_over_forum():
    """Navigational people-finder queries should not rank forum keyword matches first."""
    hn = NormalizedResult(
        title="Ask HN: How to monetize a travel site?",
        url="https://news.ycombinator.com/item?id=1",
        snippet="I've built a travel deals website in Australia over the past 7 months.",
        source="hn",
        published_at=None,
        domain="news.ycombinator.com",
        raw_rank=0,
        extra={},
    )
    directory = NormalizedResult(
        title="People Search - Australia's Free People Finder & Reunion Site",
        url="https://www.peoplesearch.com.au/",
        snippet="Free Australian search, people finder, and reunion site.",
        source="ddg",
        published_at=None,
        domain="peoplesearch.com.au",
        raw_rank=1,
        extra={},
    )
    params = RetrievalParams(top_n_after_score=10)
    hits = apply_pipeline_stages(
        "person search aus",
        "person search aus",
        [hn, directory],
        params=params,
    )
    assert len(hits) == 2
    assert "peoplesearch.com.au" in hits[0]["url"]


def test_intent_alignment_delta_people_search_forum_vs_directory():
    q = "person search aus"
    hn = NormalizedResult(
        title="Ask HN: travel",
        url="https://news.ycombinator.com/item?id=1",
        snippet="Australia",
        source="hn",
        published_at=None,
        domain="news.ycombinator.com",
        raw_rank=0,
        extra={},
    )
    good = NormalizedResult(
        title="People Search Australia",
        url="https://example.com.au/",
        snippet="people finder reunion directory",
        source="ddg",
        published_at=None,
        domain="example.com.au",
        raw_rank=0,
        extra={},
    )
    assert intent_alignment_delta(q, hn) < intent_alignment_delta(q, good)


def test_apply_pipeline_prefers_high_authority_domain():
    low = NormalizedResult(
        title="low",
        url="https://spam-casino.example/p",
        snippet="python tutorial",
        source="x",
        published_at=None,
        domain="spam-casino.example",
        raw_rank=0,
        extra={},
    )
    high = NormalizedResult(
        title="high",
        url="https://en.wikipedia.org/wiki/Python",
        snippet="python programming language",
        source="y",
        published_at=None,
        domain="en.wikipedia.org",
        raw_rank=1,
        extra={},
    )
    params = RetrievalParams(top_n_after_score=10)
    hits = apply_pipeline_stages("python", "python", [low, high], params=params)
    assert len(hits) == 2
    assert "wikipedia.org" in hits[0]["url"]


def test_aggregate_sources_runs_fetchers():
    def a():
        return [{"title": "1", "url": "https://a.com", "body": ""}]

    def b():
        return [{"title": "2", "url": "https://b.com", "body": ""}]

    async def _run():
        return await aggregate_sources({"sa": a, "sb": b}, "q", per_source_timeout=2.0, overall_timeout=3.0)

    merged = asyncio.run(_run())
    domains = {m.domain for m in merged}
    assert "a.com" in domains
    assert "b.com" in domains


def test_run_text_retrieval_pipeline_sync_smoke():
    def wiki():
        return [
            {
                "title": "Python",
                "url": "https://en.wikipedia.org/wiki/Python",
                "body": "general purpose language",
            }
        ]

    def other():
        return [{"title": "x", "url": "https://z.com/z", "body": "unrelated shopping"}]

    hits = run_text_retrieval_pipeline_sync(
        user_query="python language",
        effective_query="python language",
        fetchers={"wikipedia": wiki, "other": other},
        max_results=20,
    )
    assert len(hits) >= 1
    assert any("wikipedia" in h["url"] for h in hits)


def test_pipeline_disabled_in_default_tests_via_conftest(monkeypatch):
    """Sanity: app respects env when conftest does not patch (opt-in)."""
    monkeypatch.setenv("ABBIEY_RETRIEVAL_PIPELINE", "0")
    from app import _retrieval_pipeline_enabled

    assert _retrieval_pipeline_enabled() is False
