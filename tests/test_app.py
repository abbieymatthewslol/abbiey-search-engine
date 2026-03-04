"""Tests for abbiey.search app routes, caching, fallbacks, chat API, and feature cards."""

import json
from unittest.mock import patch, MagicMock

import pytest

from app import (
    _try_calculator, _try_color_picker, _try_unit_convert,
    _try_knowledge_panel, _BANG_MAP, _BANG_RE,
)


class TestRoutes:
    """Test basic route behavior."""

    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"abbiey.search" in resp.data

    def test_search_empty_query_shows_index(self, client):
        resp = client.get("/search?q=")
        assert resp.status_code == 200
        assert b"abbiey.search" in resp.data

    def test_search_with_query(self, client, mock_ddg):
        resp = client.get("/search?q=python")
        assert resp.status_code == 200
        assert b"python" in resp.data.lower()

    def test_search_ajax_returns_json(self, client, mock_ddg):
        resp = client.get(
            "/search?q=python&page=1&type=text",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "results" in data
        assert "has_more" in data
        assert "page" in data

    def test_search_invalid_type_defaults_to_text(self, client, mock_ddg):
        resp = client.get("/search?q=test&type=invalid")
        assert resp.status_code == 200

    def test_search_images(self, client, mock_ddg):
        resp = client.get("/search?q=cats&type=images")
        assert resp.status_code == 200

    def test_search_news(self, client, mock_ddg):
        resp = client.get("/search?q=tech&type=news")
        assert resp.status_code == 200

    def test_search_videos(self, client, mock_ddg):
        resp = client.get("/search?q=music&type=videos")
        assert resp.status_code == 200


class TestQueryLimits:
    """Test query length validation."""

    def test_long_query_returns_400(self, client):
        long_query = "a" * 2001
        resp = client.get(f"/search?q={long_query}")
        assert resp.status_code == 400

    def test_max_length_query_ok(self, client, mock_ddg):
        query = "a" * 2000
        resp = client.get(f"/search?q={query}")
        assert resp.status_code == 200

    def test_entity_api_long_query_returns_400(self, client):
        long_query = "a" * 2001
        resp = client.get(f"/api/entity?q={long_query}")
        assert resp.status_code == 400


class TestSuggestionsAPI:
    """Test the suggestions/autocomplete endpoint."""

    def test_empty_query_returns_empty(self, client):
        resp = client.get("/api/suggestions?q=")
        assert resp.get_json() == []

    def test_long_query_returns_empty(self, client):
        resp = client.get(f"/api/suggestions?q={'a' * 201}")
        assert resp.get_json() == []


class TestEntityAPI:
    """Test the entity detection endpoint."""

    def test_empty_query(self, client):
        resp = client.get("/api/entity?q=")
        data = resp.get_json()
        assert data["entities"] == []

    def test_phone_detection(self, client):
        resp = client.get("/api/entity?q=+1 555-123-4567")
        data = resp.get_json()
        assert len(data["entities"]) > 0
        assert data["entities"][0]["type"] == "phone"

    def test_email_detection(self, client):
        resp = client.get("/api/entity?q=test@example.com")
        data = resp.get_json()
        types = [e["type"] for e in data["entities"]]
        assert "email" in types


class TestCaching:
    """Test TTL result caching."""

    def test_results_are_cached(self, client, mock_ddg):
        # First request
        client.get("/search?q=cache_test", headers={"X-Requested-With": "XMLHttpRequest"})
        call_count_1 = mock_ddg.text.call_count

        # Second request (should hit cache)
        client.get("/search?q=cache_test", headers={"X-Requested-With": "XMLHttpRequest"})
        call_count_2 = mock_ddg.text.call_count

        # DDG should only be called once
        assert call_count_2 == call_count_1

    def test_different_queries_not_cached(self, client, mock_ddg):
        client.get("/search?q=query1", headers={"X-Requested-With": "XMLHttpRequest"})
        call_count_1 = mock_ddg.text.call_count

        client.get("/search?q=query2", headers={"X-Requested-With": "XMLHttpRequest"})
        call_count_2 = mock_ddg.text.call_count

        assert call_count_2 > call_count_1

    def test_different_types_not_cached(self, client, mock_ddg):
        client.get("/search?q=test&type=text", headers={"X-Requested-With": "XMLHttpRequest"})
        text_calls = mock_ddg.text.call_count

        client.get("/search?q=test&type=images", headers={"X-Requested-With": "XMLHttpRequest"})
        image_calls = mock_ddg.images.call_count

        assert text_calls > 0
        assert image_calls > 0


class TestErrorHandlers:
    """Test custom error pages."""

    def test_404_page(self, client):
        resp = client.get("/this-does-not-exist")
        assert resp.status_code == 404
        assert b"Not Found" in resp.data

    def test_error_page_has_back_link(self, client):
        resp = client.get("/nonexistent")
        assert b"Back to Search" in resp.data


class TestFallbackChain:
    """Test the multi-layer fallback mechanism."""

    def test_ddg_failure_falls_to_searxng(self, client, mock_httpx):
        with patch("app._try_ddg", side_effect=Exception("DDG down")):
            # Mock SearXNG to return results
            searx_resp = MagicMock()
            searx_resp.status_code = 200
            searx_resp.raise_for_status = MagicMock()
            searx_resp.json.return_value = {
                "results": [{"title": "SearXNG Result", "url": "https://searx.test/1", "content": "From SearXNG"}]
            }
            mock_httpx.get.return_value = searx_resp

            resp = client.get("/search?q=fallback_test", headers={"X-Requested-With": "XMLHttpRequest"})
            data = resp.get_json()
            assert len(data["results"]) > 0

    def test_all_engines_fail_returns_empty(self, client):
        with patch("app._try_ddg", side_effect=Exception("fail")), \
             patch("app._try_wikipedia", return_value=[]), \
             patch("app._try_wiby", return_value=[]), \
             patch("app._try_mojeek", return_value=[]), \
             patch("app._try_ddg_instant", return_value=[]):

            resp = client.get("/search?q=obscure_xyz", headers={"X-Requested-With": "XMLHttpRequest"})
            data = resp.get_json()
            assert data["results"] == []
            assert data["has_more"] is False


class TestSearchOperators:
    """Test search operator parsing."""

    def test_site_operator(self, client, mock_ddg):
        resp = client.get("/search?q=python+site:reddit.com")
        assert resp.status_code == 200

    def test_filetype_operator(self, client, mock_ddg):
        resp = client.get("/search?q=report+filetype:pdf")
        assert resp.status_code == 200

    def test_operators_shown_in_response(self, client, mock_ddg):
        resp = client.get("/search?q=test+site:example.com")
        assert resp.status_code == 200
        assert b"site" in resp.data.lower()


class TestRegionSupport:
    """Test region/language awareness."""

    def test_region_parameter(self, client, mock_ddg):
        resp = client.get("/search?q=news&region=de-de&lang=de")
        assert resp.status_code == 200

    def test_empty_region_ok(self, client, mock_ddg):
        resp = client.get("/search?q=test&region=&lang=")
        assert resp.status_code == 200


class TestEntityDedup:
    """Test entity results deduplication vs main results."""

    def test_entity_urls_removed_from_main(self, client):
        """When entity results contain URLs, those URLs should not appear in main results."""
        entity_results = [
            {"title": "Entity R", "url": "https://dup.example.com/1", "body": "dup"},
        ]
        main_results = [
            {"title": "Main 1", "url": "https://dup.example.com/1", "body": "same url"},
            {"title": "Main 2", "url": "https://unique.example.com/2", "body": "unique"},
        ]

        with patch("app._fetch_results") as mock_fetch:
            # First call: main results. Second+: entity results.
            mock_fetch.side_effect = [
                {"results": main_results, "has_more": False, "page": 1},
                {"results": entity_results, "has_more": False, "page": 1},
            ]
            with patch("app.detect_entities") as mock_detect:
                from entity_parser import Entity
                mock_detect.return_value = [Entity("email", "test@test.com", "test@test.com", 0.98, {"username": "test", "domain": "test.com"})]

                with patch("app.build_search_queries") as mock_queries:
                    mock_queries.return_value = [{"label": "Test", "query": "test", "type": "text"}]
                    with patch("app.primary_entity") as mock_primary:
                        mock_primary.return_value = Entity("email", "test@test.com", "test@test.com", 0.98, {"username": "test", "domain": "test.com"})

                        resp = client.get("/search?q=test@test.com")
                        assert resp.status_code == 200


class TestChatAPI:
    """Test the AI research assistant chat endpoint."""

    def test_chat_missing_fields(self, client):
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 400

    def test_chat_missing_message(self, client):
        resp = client.post("/api/chat", json={"query": "test"})
        assert resp.status_code == 400

    def test_chat_success(self, client, mock_ddg, mock_chat):
        resp = client.post("/api/chat", json={
            "query": "python programming",
            "message": "What is Python?",
            "history": [],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "response" in data
        assert mock_chat.called

    def test_chat_with_history(self, client, mock_ddg, mock_chat):
        resp = client.post("/api/chat", json={
            "query": "test topic",
            "message": "follow up question",
            "history": [
                {"role": "user", "content": "first question"},
                {"role": "assistant", "content": "first answer"},
            ],
        })
        assert resp.status_code == 200
        # Verify history was passed in messages
        call_args = mock_chat.call_args[0][0]  # first positional arg (messages list)
        roles = [m["role"] for m in call_args]
        assert roles.count("user") >= 3  # context + history + current message

    def test_chat_long_message(self, client):
        resp = client.post("/api/chat", json={
            "query": "test",
            "message": "a" * 2001,
            "history": [],
        })
        assert resp.status_code == 400

    def test_chat_falls_back_to_extractive(self, client, mock_ddg, mock_chat):
        """When AI chat fails, extractive research fallback returns 200."""
        mock_chat.side_effect = Exception("Service down")
        resp = client.post("/api/chat", json={
            "query": "test",
            "message": "hello",
            "history": [],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "response" in data

    def test_chat_total_failure_returns_503(self, client, mock_ddg, mock_chat):
        """When both AI chat and extractive fallback fail, returns 503."""
        mock_chat.side_effect = Exception("Service down")
        with patch("app._extractive_research", side_effect=Exception("fallback broken")):
            resp = client.post("/api/chat", json={
                "query": "test",
                "message": "hello",
                "history": [],
            })
            assert resp.status_code == 503


# =====================================================================
# BANG COMMANDS
# =====================================================================
class TestBangCommands:
    """Test bang redirect functionality."""

    def test_bang_regex_matches(self):
        m = _BANG_RE.match("!w python")
        assert m is not None
        assert m.group(1) == "w"
        assert m.group(2) == "python"

    def test_bang_regex_with_spaces(self):
        m = _BANG_RE.match("!yt funny cats")
        assert m is not None
        assert m.group(1) == "yt"
        assert m.group(2) == "funny cats"

    def test_bang_map_has_required_entries(self):
        required = ["w", "yt", "gh", "so", "r", "a", "g", "tw", "npm", "pypi", "mdn", "maps"]
        for bang in required:
            assert bang in _BANG_MAP, f"Missing bang: !{bang}"

    def test_bang_redirect_wikipedia(self, client):
        resp = client.get("/search?q=!w+python")
        assert resp.status_code == 302
        assert "wikipedia.org" in resp.headers["Location"]
        assert "python" in resp.headers["Location"]

    def test_bang_redirect_youtube(self, client):
        resp = client.get("/search?q=!yt+music")
        assert resp.status_code == 302
        assert "youtube.com" in resp.headers["Location"]

    def test_bang_redirect_github(self, client):
        resp = client.get("/search?q=!gh+flask")
        assert resp.status_code == 302
        assert "github.com" in resp.headers["Location"]

    def test_unknown_bang_does_normal_search(self, client, mock_ddg):
        resp = client.get("/search?q=!zz+something")
        assert resp.status_code == 200  # Normal search, not a redirect

    def test_bang_no_query_does_normal_search(self, client, mock_ddg):
        """Bang with no search term should do normal search."""
        resp = client.get("/search?q=!w")
        assert resp.status_code == 200

    def test_homepage_shows_bang_hint(self, client):
        resp = client.get("/")
        assert b"!w" in resp.data
        assert b"!yt" in resp.data
        assert b"!gh" in resp.data


# =====================================================================
# CALCULATOR
# =====================================================================
class TestCalculator:
    """Test math expression evaluation."""

    def test_basic_addition(self):
        result = _try_calculator("2+3")
        assert result is not None
        assert result["result"] == "5"

    def test_subtraction(self):
        result = _try_calculator("10-3")
        assert result is not None
        assert result["result"] == "7"

    def test_multiplication(self):
        result = _try_calculator("6*7")
        assert result is not None
        assert result["result"] == "42"

    def test_division(self):
        result = _try_calculator("10/4")
        assert result is not None
        assert result["result"] == "2.5"

    def test_power(self):
        result = _try_calculator("2^10")
        assert result is not None
        assert result["result"] == "1024"

    def test_modulo(self):
        result = _try_calculator("10%3")
        assert result is not None
        assert result["result"] == "1"

    def test_sqrt(self):
        result = _try_calculator("sqrt(144)")
        assert result is not None
        assert result["result"] == "12"

    def test_sin_pi(self):
        result = _try_calculator("sin(pi/2)")
        assert result is not None
        assert float(result["result"]) == pytest.approx(1.0)

    def test_cos(self):
        result = _try_calculator("cos(0)")
        assert result is not None
        assert result["result"] == "1"

    def test_log(self):
        result = _try_calculator("log(1)")
        assert result is not None
        assert result["result"] == "0"

    def test_nested_expression(self):
        result = _try_calculator("sqrt(16) + 2^3")
        assert result is not None
        assert result["result"] == "12"

    def test_pi_constant(self):
        result = _try_calculator("pi*2")
        assert result is not None
        assert float(result["result"]) == pytest.approx(6.2831853072)

    def test_rejects_plain_text(self):
        assert _try_calculator("hello world") is None

    def test_rejects_short_input(self):
        assert _try_calculator("5") is None

    def test_rejects_import_attempt(self):
        assert _try_calculator("__import__('os')") is None

    def test_rejects_attribute_access(self):
        assert _try_calculator("pow.__class__") is None

    def test_rejects_dunder(self):
        assert _try_calculator("().__class__.__bases__") is None

    def test_preserves_expression(self):
        result = _try_calculator("2^10")
        assert result["expression"] == "2^10"

    def test_calculator_card_rendered(self, client, mock_ddg):
        resp = client.get("/search?q=sqrt(144)&type=text")
        assert resp.status_code == 200
        assert b"calculator-card" in resp.data
        assert b"12" in resp.data


# =====================================================================
# COLOR PICKER
# =====================================================================
class TestColorPicker:
    """Test color detection and conversion."""

    def test_hex_6digit(self):
        result = _try_color_picker("#FF5733")
        assert result is not None
        assert result["hex"] == "#ff5733"
        assert result["r"] == 255
        assert result["g"] == 87
        assert result["b"] == 51

    def test_hex_3digit(self):
        result = _try_color_picker("#F00")
        assert result is not None
        assert result["hex"] == "#ff0000"
        assert result["r"] == 255
        assert result["g"] == 0
        assert result["b"] == 0

    def test_rgb_format(self):
        result = _try_color_picker("rgb(255, 87, 51)")
        assert result is not None
        assert result["hex"] == "#ff5733"

    def test_rgb_values_out_of_range(self):
        assert _try_color_picker("rgb(300, 0, 0)") is None

    def test_hsl_format(self):
        result = _try_color_picker("hsl(0, 100%, 50%)")
        assert result is not None
        assert result["r"] == 255

    def test_hex_rgb_hsl_all_present(self):
        result = _try_color_picker("#00FF00")
        assert "hex" in result
        assert "rgb_str" in result
        assert "hsl_str" in result

    def test_luminance_light(self):
        result = _try_color_picker("#FFFFFF")
        assert result["is_light"] is True

    def test_luminance_dark(self):
        result = _try_color_picker("#000000")
        assert result["is_light"] is False

    def test_rejects_non_color(self):
        assert _try_color_picker("hello") is None
        assert _try_color_picker("python tutorial") is None

    def test_rejects_invalid_hex_length(self):
        assert _try_color_picker("#FFFF") is None  # 4 chars

    def test_color_card_rendered(self, client, mock_ddg):
        resp = client.get("/search?q=%23FF5733&type=text")
        assert resp.status_code == 200
        assert b"color-card" in resp.data
        assert b"color-swatch-preview" in resp.data

    def test_black(self):
        result = _try_color_picker("#000000")
        assert result["hex"] == "#000000"
        assert result["rgb_str"] == "rgb(0, 0, 0)"

    def test_white(self):
        result = _try_color_picker("#FFFFFF")
        assert result["hex"] == "#ffffff"
        assert result["rgb_str"] == "rgb(255, 255, 255)"


# =====================================================================
# UNIT CONVERSION
# =====================================================================
class TestUnitConversion:
    """Test unit conversion logic."""

    def test_miles_to_km(self):
        result = _try_unit_convert("5 miles in km")
        assert result is not None
        assert abs(result["result"] - 8.0467) < 0.01

    def test_km_to_miles(self):
        result = _try_unit_convert("10 km to miles")
        assert result is not None
        assert abs(result["result"] - 6.2137) < 0.01

    def test_fahrenheit_to_celsius(self):
        result = _try_unit_convert("100 fahrenheit to celsius")
        assert result is not None
        assert abs(result["result"] - 37.7778) < 0.01

    def test_celsius_to_fahrenheit(self):
        result = _try_unit_convert("0 celsius to fahrenheit")
        assert result is not None
        assert result["result"] == 32

    def test_pounds_to_kg(self):
        result = _try_unit_convert("10 pounds to kg")
        assert result is not None
        assert abs(result["result"] - 4.53592) < 0.01

    def test_feet_to_meters(self):
        result = _try_unit_convert("6 feet to m")
        assert result is not None
        assert abs(result["result"] - 1.8288) < 0.01

    def test_gallons_to_liters(self):
        result = _try_unit_convert("1 gallon to liters")
        assert result is not None
        assert abs(result["result"] - 3.78541) < 0.01

    def test_gb_to_mb(self):
        result = _try_unit_convert("2 gb to mb")
        assert result is not None
        assert result["result"] == 2048

    def test_mph_to_kph(self):
        result = _try_unit_convert("60 mph to kph")
        assert result is not None
        assert abs(result["result"] - 96.5604) < 0.1

    def test_inches_to_cm(self):
        result = _try_unit_convert("12 inches to cm")
        assert result is not None
        assert abs(result["result"] - 30.48) < 0.01

    def test_result_formatted(self):
        result = _try_unit_convert("5 miles in km")
        assert "result_formatted" in result
        assert isinstance(result["result_formatted"], str)

    def test_rejects_unknown_units(self):
        assert _try_unit_convert("5 widgets in things") is None

    def test_rejects_non_conversion(self):
        assert _try_unit_convert("hello world") is None

    def test_unit_card_rendered(self, client, mock_ddg):
        resp = client.get("/search?q=5+miles+in+km&type=text")
        assert resp.status_code == 200
        assert b"convert-card" in resp.data

    def test_preserves_from_to_units(self):
        result = _try_unit_convert("5 miles in km")
        assert result["from_unit"] == "miles"
        assert result["to_unit"] == "km"
        assert result["value"] == "5"

    def test_celsius_to_kelvin(self):
        result = _try_unit_convert("0 celsius to kelvin")
        assert result is not None
        assert result["result"] == 273.15


# =====================================================================
# KNOWLEDGE PANELS
# =====================================================================
class TestKnowledgePanels:
    """Test Wikipedia knowledge panel API."""

    def test_knowledge_panel_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "query": {
                "pages": {
                    "123": {
                        "title": "Albert Einstein",
                        "extract": "Albert Einstein was a German-born theoretical physicist who is widely held to be one of the greatest and most influential scientists of all time.",
                        "thumbnail": {"source": "https://upload.wikimedia.org/thumb.jpg"},
                    }
                }
            }
        }
        with patch("app.httpx.get", return_value=mock_resp):
            result = _try_knowledge_panel("Albert Einstein")
        assert result is not None
        assert result["title"] == "Albert Einstein"
        assert "Einstein" in result["extract"]
        assert result["image_url"] == "https://upload.wikimedia.org/thumb.jpg"
        assert "wikipedia.org" in result["page_url"]

    def test_knowledge_panel_not_found(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"query": {"pages": {"-1": {"missing": ""}}}}
        with patch("app.httpx.get", return_value=mock_resp):
            result = _try_knowledge_panel("xyznonexistent")
        assert result is None

    def test_knowledge_panel_short_extract_rejected(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "query": {"pages": {"1": {"title": "X", "extract": "Too short."}}}
        }
        with patch("app.httpx.get", return_value=mock_resp):
            result = _try_knowledge_panel("something")
        assert result is None

    def test_knowledge_panel_rejects_long_queries(self):
        assert _try_knowledge_panel("one two three four five") is None

    def test_knowledge_panel_rejects_operators(self):
        assert _try_knowledge_panel("site:example.com") is None

    def test_knowledge_panel_network_error(self):
        with patch("app.httpx.get", side_effect=Exception("Network error")):
            result = _try_knowledge_panel("Python")
        assert result is None

    def test_knowledge_panel_rendered(self, client, mock_ddg):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "query": {
                "pages": {
                    "456": {
                        "title": "Flask",
                        "extract": "Flask is a micro web framework written in Python. It is classified as a microframework because it does not require particular tools or libraries.",
                        "thumbnail": {"source": "https://upload.wikimedia.org/flask.jpg"},
                    }
                }
            }
        }
        with patch("app.httpx.get", return_value=mock_resp):
            resp = client.get("/search?q=Flask&type=text")
        assert resp.status_code == 200
        assert b"knowledge-panel" in resp.data


# =====================================================================
# WEATHER CARDS
# =====================================================================
class TestWeatherCards:
    """Test weather card rendering via mocked APIs."""

    def test_weather_card_rendered(self, client, mock_ddg):
        geo_resp = MagicMock()
        geo_resp.json.return_value = {
            "results": [{"name": "London", "country": "UK", "latitude": 51.5, "longitude": -0.12}]
        }
        wx_resp = MagicMock()
        wx_resp.json.return_value = {
            "current": {
                "temperature_2m": 15, "weather_code": 2,
                "wind_speed_10m": 12, "relative_humidity_2m": 65,
            },
            "daily": {
                "time": ["2026-02-28", "2026-03-01", "2026-03-02"],
                "temperature_2m_max": [16, 18, 14],
                "temperature_2m_min": [8, 10, 6],
                "weather_code": [2, 0, 61],
            },
        }
        with patch("app.httpx.get", side_effect=[geo_resp, wx_resp]):
            resp = client.get("/search?q=weather+London&type=text")
        assert resp.status_code == 200
        assert b"weather-card" in resp.data
        assert b"London" in resp.data

    def test_weather_unknown_location(self, client, mock_ddg):
        geo_resp = MagicMock()
        geo_resp.json.return_value = {}  # No results
        with patch("app.httpx.get", return_value=geo_resp):
            resp = client.get("/search?q=weather+xyznoplace&type=text")
        assert resp.status_code == 200
        assert b"weather-card" not in resp.data


# =====================================================================
# AI SUMMARY ENDPOINT
# =====================================================================
class TestAISummary:
    """Test the /api/ai-summary endpoint."""

    def test_ai_summary_success(self, client, mock_ddg, mock_chat):
        mock_chat.return_value = "Python is a programming language [1]. It was created by Guido [2]."
        resp = client.get("/api/ai-summary?q=python")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data
        assert "sources" in data
        assert len(data["sources"]) > 0

    def test_ai_summary_empty_query(self, client):
        resp = client.get("/api/ai-summary?q=")
        assert resp.status_code == 400

    def test_ai_summary_long_query(self, client):
        resp = client.get(f"/api/ai-summary?q={'a' * 2001}")
        assert resp.status_code == 400

    def test_ai_summary_sources_have_urls(self, client, mock_ddg, mock_chat):
        mock_chat.return_value = "Summary text."
        resp = client.get("/api/ai-summary?q=test")
        data = resp.get_json()
        for source in data["sources"]:
            assert "title" in source
            assert "url" in source

    def test_ai_summary_fallback_on_ai_failure(self, client, mock_ddg, mock_chat):
        """When AI fails, should fallback to extractive summary."""
        mock_chat.side_effect = Exception("AI down")
        resp = client.get("/api/ai-summary?q=test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data

    def test_ai_summary_no_results(self, client):
        """When no search results exist, return 404."""
        with patch("app._fetch_results", return_value={"results": [], "has_more": False, "page": 1}):
            resp = client.get("/api/ai-summary?q=xyznonexistent123")
        assert resp.status_code == 404


# =====================================================================
# PRIVACY BADGE
# =====================================================================
class TestPrivacyBadge:
    """Test privacy badge rendering in HTML."""

    def test_privacy_badge_on_homepage(self, client):
        resp = client.get("/")
        assert b"privacy-badge" in resp.data
        assert b"0 trackers" in resp.data

    def test_privacy_popover_on_homepage(self, client):
        resp = client.get("/")
        assert b"privacy-popover" in resp.data
        assert b"cookies set" in resp.data
        assert b"searches logged" in resp.data
        assert b"data shared" in resp.data

    def test_privacy_badge_on_search_page(self, client, mock_ddg):
        resp = client.get("/search?q=test")
        assert b"privacy-badge" in resp.data

    def test_privacy_google_comparison(self, client):
        resp = client.get("/")
        assert b"Google collects" in resp.data

    def test_privacy_tagline(self, client):
        resp = client.get("/")
        assert b"Your privacy is our priority" in resp.data


# =====================================================================
# FEATURE CARD MUTUAL EXCLUSION
# =====================================================================
class TestFeatureCardLogic:
    """Test that feature cards don't conflict with each other."""

    def test_color_prevents_calculator(self, client, mock_ddg):
        """A hex color query should show color card, not calculator."""
        resp = client.get("/search?q=%23FF5733&type=text")
        assert b"color-card" in resp.data
        assert b"calculator-card" not in resp.data

    def test_calculator_shown_for_math(self, client, mock_ddg):
        resp = client.get("/search?q=2%2B2&type=text")
        assert b"calculator-card" in resp.data
        assert b"color-card" not in resp.data

    def test_no_cards_on_images_tab(self, client, mock_ddg):
        """Feature cards should only appear on text tab."""
        resp = client.get("/search?q=sqrt(144)&type=images")
        assert b"calculator-card" not in resp.data

    def test_ai_summary_only_on_text_tab(self, client, mock_ddg):
        resp = client.get("/search?q=test&type=images")
        assert b"ai-summary-card" not in resp.data

    def test_ai_summary_on_text_tab(self, client, mock_ddg):
        resp = client.get("/search?q=test&type=text")
        assert b"ai-summary-card" in resp.data
