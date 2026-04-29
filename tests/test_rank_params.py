"""Tests for text ranking mode normalization."""

from retrieval.rank_params import normalize_rank_mode, rank_mode_cache_segment


def test_normalize_rank_mode_defaults():
    assert normalize_rank_mode(None) == "neutral"
    assert normalize_rank_mode("") == "neutral"
    assert normalize_rank_mode("  INVALID  ") == "neutral"


def test_normalize_rank_mode_aliases():
    assert normalize_rank_mode("raw") == "raw"
    assert normalize_rank_mode("LLM") == "llm"
    assert normalize_rank_mode("unfiltered") == "raw"
    assert normalize_rank_mode("off") == "raw"


def test_rank_mode_cache_segment():
    assert "|rm=raw" in rank_mode_cache_segment("raw")
    assert rank_mode_cache_segment("neutral") == "|rm=neutral"
