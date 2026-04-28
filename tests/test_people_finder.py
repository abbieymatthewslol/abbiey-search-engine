"""Tests for people_finder questionnaire helpers."""

from people_finder import (
    build_people_finder_query_hint,
    parse_people_finder_args,
    people_finder_cache_suffix,
    people_pf_params_only_fragment,
)


class _Args:
    """Minimal request.args stand-in."""

    def __init__(self, d):
        self._d = d

    def get(self, k, default=None):
        return self._d.get(k, default)


def test_parse_and_build_hint():
    m = _Args(
        {
            "pf_city": "Austin",
            "pf_country": "US",
            "pf_intent": "professional",
        }
    )
    pf = parse_people_finder_args(m)
    assert pf is not None
    assert pf["city"] == "Austin"
    q = build_people_finder_query_hint("Jane Doe", pf)
    assert "Jane Doe" in q
    assert "Austin" in q

    assert "|pfv1:" in people_finder_cache_suffix(pf)
    frag = people_pf_params_only_fragment(pf)
    assert "pf_city=" in frag


def test_parse_empty_returns_none():
    assert parse_people_finder_args(_Args({})) is None
