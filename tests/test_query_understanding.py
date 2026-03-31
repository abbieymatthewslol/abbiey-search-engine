"""Tests for synonym normalization, intent classification, and pattern parsing."""

import pytest

from entity_parser import detect_entities, primary_entity
from query_understanding import (
    build_backend_search_query,
    classify_intent,
    normalize_synonyms,
    parse_query_patterns,
    place_category_matches,
    preprocess_query,
    query_ui_hints,
    resolve_location_for_search,
    should_enable_ai_summary,
)


def test_normalize_op_shop_to_thrift_store():
    out, applied = normalize_synonyms("op shop near me")
    assert "thrift store" in out.lower()
    assert any("op shop" in a for a, _ in applied)


def test_preprocess_includes_intent_local():
    prep = preprocess_query("pharmacy near me")
    assert prep.intent == "local_search"
    assert prep.pattern is not None
    assert prep.pattern.kind == "near_me"


def test_preprocess_best_in_pattern():
    prep = preprocess_query("best pizza in brooklyn")
    assert prep.pattern is not None
    assert prep.pattern.kind == "best_in"
    assert "pizza" in prep.pattern.subject.lower()
    assert "brooklyn" in prep.pattern.location.lower()


def test_preprocess_closest_pattern():
    prep = preprocess_query("closest gas station")
    assert prep.pattern is not None
    assert prep.pattern.kind == "closest"
    assert "gas" in prep.pattern.subject.lower()


def test_intent_transactional():
    assert classify_intent("buy iphone cheap", "buy iphone cheap") == "transactional"


def test_intent_navigational_login():
    assert classify_intent("github login", "github login") == "navigational"


def test_intent_informational_default():
    assert classify_intent("how does photosynthesis work", "x") == "informational"


def test_place_category_after_synonym():
    prep = preprocess_query("op shop")
    entities = detect_entities("op shop", _preprocessed=prep)
    types = [e.type for e in entities]
    assert "place_category" in types
    pc = next(e for e in entities if e.type == "place_category")
    assert pc.normalized == "thrift_store"


def test_detect_entities_phone_still_first():
    entities = detect_entities("+1 555-123-4567")
    assert entities[0].type == "phone"


def test_place_category_matches_non_overlapping():
    m = place_category_matches("thrift store and gas station downtown")
    keys = {x["category_key"] for x in m}
    assert "thrift_store" in keys
    assert "gas_station" in keys


def test_parse_near_poi():
    p = parse_query_patterns("coffee near Union Square")
    assert p is not None
    assert p.kind == "near_poi"
    assert "coffee" in p.subject.lower()


def test_primary_prefers_phone_over_place():
    # Word after the number must not start with a–f (phone detector skips “hex-adjacent” matches).
    prep = preprocess_query("call +1 555-123-4567 today at the thrift store")
    entities = detect_entities("call +1 555-123-4567 today at the thrift store", _preprocessed=prep)
    prim = primary_entity(entities)
    assert prim is not None
    assert prim.type == "phone"


def test_build_backend_query_closest_op_shop():
    prep = preprocess_query("closest op shop")
    loc = resolve_location_for_search(prep, None, None, None)
    q = build_backend_search_query("closest op shop", prep, loc)
    assert "near me" in q.lower() and "sorted by distance" in q.lower()
    assert "thrift" in q.lower()


def test_ai_summary_disabled_for_closest_pizza():
    prep = preprocess_query("closest pizza")
    assert should_enable_ai_summary(prep) is False


def test_ai_summary_enabled_for_what_is_x():
    prep = preprocess_query("what is photosynthesis")
    assert should_enable_ai_summary(prep) is True


def test_query_ui_hints_local():
    prep = preprocess_query("gas station near me")
    ui = query_ui_hints(prep)
    assert ui["local_intent"] is True
    assert ui["show_ai_summary"] is False
