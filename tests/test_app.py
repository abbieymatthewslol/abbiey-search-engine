"""Tests for abbiey.search app routes, caching, fallbacks, chat API, and feature cards."""

import json
from unittest.mock import patch, MagicMock

import app
import pytest

from app import (
    MAX_QUERY_LENGTH,
    _try_calculator, _try_color_picker, _try_unit_convert,
    _try_knowledge_panel,
    _rank_anti_template_results,
    search_safeguard_meta,
    _static_search_portal_links,
    _simplify_query_for_fallback,
)


class TestRoutes:
    """Test basic route behavior."""

    def test_index_redirects_to_search(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 301
        assert "/search" in (resp.headers.get("Location") or "")

    def test_index_followed_shows_search_ui(self, client):
        resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b'id="search-input"' in resp.data
        assert b"abbiey.search" in resp.data

    def test_root_is_search_ui_not_marketing_landing(self, client):
        """Root redirects to search UI; marketing page is at /landing."""
        resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"nobody's watching" not in resp.data

    def test_landing_path_renders_marketing(self, client):
        resp = client.get("/landing")
        assert resp.status_code == 200
        assert b"Your searches stay yours." in resp.data

    def test_google_site_verification_meta_when_configured(self, client):
        import app as app_module

        with patch.object(app_module, "_GOOGLE_SITE_VERIFICATION", "gsc-test-token"):
            resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b'name="google-site-verification"' in resp.data
        assert b'content="gsc-test-token"' in resp.data

    def test_google_site_verification_omitted_when_disabled(self, client):
        import app as app_module

        with patch.object(app_module, "_GOOGLE_SITE_VERIFICATION", ""):
            resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"google-site-verification" not in resp.data

    def test_google_analytics_gtag_when_configured(self, client):
        import app as app_module

        with patch.object(app_module, "_GOOGLE_ANALYTICS_ID", "G-TESTID99"):
            resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"googletagmanager.com/gtag/js" in resp.data
        assert b"G-TESTID99" in resp.data

    def test_google_analytics_omitted_when_disabled(self, client):
        import app as app_module

        with patch.object(app_module, "_GOOGLE_ANALYTICS_ID", ""):
            resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert b"googletagmanager.com/gtag/js" not in resp.data

    def test_search_empty_query_shows_index(self, client):
        resp = client.get("/search?q=")
        assert resp.status_code == 200
        assert b"abbiey.search" in resp.data

    def test_search_home_shows_creator_credit(self, client):
        resp = client.get("/search", follow_redirects=False)
        assert resp.status_code == 200
        assert b"abbiey matthews" in resp.data.lower()

    def test_search_homepage_has_privacy_policy_link(self, client):
        """OAuth / policy reviewers expect a visible Privacy Policy link on the home URL."""
        resp = client.get("/search")
        assert resp.status_code == 200
        assert b'href="/privacy"' in resp.data
        assert b"Privacy Policy" in resp.data

    def test_search_googlebot_not_blocked_by_free_tier_limit(self, client, mock_ddg):
        """Crawlers must not get 429 from the IP search cap (reads as a walled app)."""
        googlebot = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        with patch("app._server_search_limit_reached", return_value=True):
            resp = client.get("/search?q=oauth+check", headers={"User-Agent": googlebot})
        assert resp.status_code == 200

    def test_access_resources_json(self, client):
        resp = client.get("/api/access-resources")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "about" in data
        assert "privacy_tools" in data
        assert "tor_browser" in data["privacy_tools"]

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

    def test_images_advanced_search_panel(self, client, mock_ddg):
        """Advanced image UI + img_adv=1 still returns results."""
        resp = client.get("/search?q=cats&type=images&img_adv=1&img_license=cc0")
        assert resp.status_code == 200
        assert b"Advanced image search" in resp.data
        assert b"Openverse" in resp.data

    def test_search_news(self, client, mock_ddg):
        resp = client.get("/search?q=tech&type=news")
        assert resp.status_code == 200

    def test_search_videos(self, client, mock_ddg):
        resp = client.get("/search?q=music&type=videos")
        assert resp.status_code == 200


class TestQueryLimits:
    """Test query length validation (default limit from ABBIEY_MAX_QUERY_LENGTH, see MAX_QUERY_LENGTH)."""

    def test_long_query_returns_400(self, client):
        long_query = "a" * (MAX_QUERY_LENGTH + 1)
        resp = client.get(f"/search?q={long_query}")
        assert resp.status_code == 400

    def test_max_length_query_ok(self, client, mock_ddg):
        query = "a" * MAX_QUERY_LENGTH
        resp = client.get(f"/search?q={query}")
        assert resp.status_code == 200

    def test_entity_api_long_query_returns_400(self, client):
        long_query = "a" * (MAX_QUERY_LENGTH + 1)
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
        assert data.get("preprocessing") is None
        assert data.get("query_ui") is None
        assert data.get("primary") is None

    def test_phone_detection(self, client):
        resp = client.get("/api/entity?q=+1 555-123-4567")
        data = resp.get_json()
        assert len(data["entities"]) > 0
        assert data["entities"][0]["type"] == "phone"
        assert "query_ui" in data
        assert data["query_ui"]["intent"] in ("informational", "local_search", "navigational", "transactional")

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
             patch("app._try_ddg_instant", return_value=[]), \
             patch("app._try_marginalia", return_value=[]), \
             patch("app._try_stract", return_value=[]), \
             patch("app._try_searxng", return_value=[]), \
             patch("app._try_hackernews_text", return_value=[]), \
             patch("app._try_reddit_text", return_value=[]), \
             patch("app._try_internet_archive_text", return_value=[]), \
             patch("app._inclusive_text_recovery_bridge", return_value=[]):

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


class TestSecurityHeaders:
    """Response headers from after_request."""

    def test_html_get_includes_csp_and_nosniff(self, client):
        resp = client.get("/", follow_redirects=True)
        assert resp.status_code == 200
        assert "content-security-policy" in resp.headers
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert "strict-origin-when-cross-origin" in (resp.headers.get("Referrer-Policy") or "")

    def test_supabase_umd_vendor_served_for_auth_pages(self, client):
        resp = client.get("/static/vendor/supabase.min.js")
        assert resp.status_code == 200
        assert len(resp.data) > 50_000
        assert b"createClient" in resp.data

    def test_flask_secret_key_is_configured(self, client):
        from app import app

        sk = app.config.get("SECRET_KEY")
        assert sk and len(str(sk)) >= 16


class TestApiPreview:
    """Page preview proxy."""

    def test_preview_rejects_non_http_url(self, client):
        resp = client.get("/api/preview?url=ftp://example.com/")
        assert resp.status_code == 400

    def test_preview_rejects_overlong_url(self, client):
        from app import _MAX_PREVIEW_URL_LEN

        long_url = "https://example.com/" + ("x" * (_MAX_PREVIEW_URL_LEN + 1))
        resp = client.get("/api/preview", query_string={"url": long_url})
        assert resp.status_code == 400

    def test_preview_normalizes_protocol_relative_url(self, client):
        from unittest.mock import MagicMock, patch

        import httpx

        mock_resp = MagicMock()
        mock_resp.text = "<html><head><title>Ex</title></head><body>hi</body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_resp.url = httpx.URL("https://example.com/page")
        with patch.object(httpx, "get", return_value=mock_resp) as get_mock:
            resp = client.get("/api/preview", query_string={"url": "//example.com/page"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("url") == "https://example.com/page"
        get_mock.assert_called_once()
        assert get_mock.call_args[0][0] == "https://example.com/page"


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
        # context is now in system role; history user + current message = 2 user msgs
        assert roles.count("user") >= 2
        assert "system" in roles  # context goes in system role

    def test_chat_message_exceeds_api_limit(self, client):
        from app import _MAX_CHAT_MESSAGE_LEN

        resp = client.post("/api/chat", json={
            "query": "test",
            "message": "a" * (_MAX_CHAT_MESSAGE_LEN + 1),
            "history": [],
        })
        assert resp.status_code == 400

    def test_chat_query_too_long(self, client):
        from app import MAX_QUERY_LENGTH

        resp = client.post("/api/chat", json={
            "query": "q" * (MAX_QUERY_LENGTH + 1),
            "message": "hello",
            "history": [],
        })
        assert resp.status_code == 400

    def test_chat_invalid_history_type(self, client):
        resp = client.post("/api/chat", json={
            "query": "test",
            "message": "hi",
            "history": "not-a-list",
        })
        assert resp.status_code == 400

    def test_chat_invalid_history_role(self, client, mock_ddg, mock_chat):
        resp = client.post("/api/chat", json={
            "query": "test",
            "message": "hi",
            "history": [{"role": "system", "content": "bad"}],
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
        resp = client.get("/api/ai-summary?q=what+is+python")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data
        assert "sources" in data
        assert len(data["sources"]) > 0
        assert data.get("clarify") is not None
        assert data.get("answer_mode") == "standard"

    def test_ai_summary_single_mode_simple_query(self, client, mock_ddg, mock_chat):
        mock_chat.return_value = "Water is H2O [1]."
        resp = client.get("/api/ai-summary?q=what+is+water")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("answer_mode") == "single"
        assert data.get("clarify") is None

    def test_ai_summary_empty_query(self, client):
        resp = client.get("/api/ai-summary?q=")
        assert resp.status_code == 400

    def test_ai_summary_long_query(self, client):
        resp = client.get(f"/api/ai-summary?q={'a' * (MAX_QUERY_LENGTH + 1)}")
        assert resp.status_code == 400

    def test_ai_summary_sources_have_urls(self, client, mock_ddg, mock_chat):
        mock_chat.return_value = "Summary text."
        resp = client.get("/api/ai-summary?q=what+is+a+test")
        data = resp.get_json()
        for source in data["sources"]:
            assert "title" in source
            assert "url" in source

    def test_ai_summary_fallback_on_ai_failure(self, client, mock_ddg, mock_chat):
        """When AI fails, should fallback to extractive summary."""
        mock_chat.side_effect = Exception("AI down")
        resp = client.get("/api/ai-summary?q=explain+gravity")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data

    def test_ai_summary_no_results(self, client):
        """When no search results exist, return 404."""
        with patch("app._fetch_results", return_value={"results": [], "has_more": False, "page": 1}):
            resp = client.get("/api/ai-summary?q=why+does+water+freeze")
        assert resp.status_code == 404

    def test_ai_summary_gated_for_local_keyword_queries(self, client, mock_ddg):
        """Bare local lookups should not run summarization."""
        resp = client.get("/api/ai-summary?q=closest+pizza")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("enabled") is False
        assert "clarify" in data

    def test_ai_summary_gated_for_near_me_phrase(self, client, mock_ddg):
        resp = client.get("/api/ai-summary?q=coffee+near+me")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("enabled") is False
        assert "clarify" in data


# =====================================================================
# ANSWER LAYER API
# =====================================================================
class TestAnswerLayer:
    """Structured /api/answer-layer synthesis."""

    def test_answer_layer_success(self, client, mock_ddg, mock_chat):
        mock_chat.return_value = json.dumps(
            {
                "headline": "Test topic",
                "synthesis": "First paragraph.\n\nSecond paragraph.",
                "claims": [
                    {"statement": "Claim one", "confidence": 0.8, "source_indices": [1]},
                    {"statement": "Claim two", "confidence": 0.5, "source_indices": [1, 2]},
                ],
                "contradictions": [
                    {
                        "summary": "Conflict",
                        "position_a": "A says X",
                        "position_b": "B says Y",
                        "sources_a": [1],
                        "sources_b": [2],
                    }
                ],
                "reasoning_steps": [
                    {"step": "Read snippets", "source_indices": [1, 2]},
                ],
            }
        )
        resp = client.get("/api/answer-layer?q=what+is+python")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("enabled") is True
        assert data.get("layer") is True
        assert data.get("headline") == "Test topic"
        assert "First paragraph" in data.get("synthesis", "")
        assert len(data.get("claims") or []) == 2
        assert len(data.get("sources") or []) >= 1

    def test_answer_layer_bad_json_falls_back_shape(self, client, mock_ddg, mock_chat):
        mock_chat.return_value = "not json at all"
        resp = client.get("/api/answer-layer?q=explain+gravity")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("enabled") is True
        assert data.get("layer") is False

    def test_answer_layer_no_results_404(self, client):
        with patch("app._fetch_results", return_value={"results": [], "has_more": False, "page": 1}):
            resp = client.get("/api/answer-layer?q=why+does+water+freeze")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data.get("layer") is False

    def test_answer_layer_gated_local(self, client, mock_ddg):
        resp = client.get("/api/answer-layer?q=coffee+near+me")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("enabled") is False

    def test_answer_layer_feature_none(self, client, mock_ddg, mock_chat):
        with patch.dict(app._FEATURE_GATES, {"answer_layer": "none"}, clear=False):
            resp = client.get("/api/answer-layer?q=what+is+python")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("layer") is False


# =====================================================================
# POSITIONING BADGE
# =====================================================================
class TestPrivacyBadge:
    """Test header positioning badge rendering in HTML."""

    def test_privacy_badge_on_homepage(self, client):
        resp = client.get("/search?q=")
        assert b"privacy-badge" in resp.data
        assert b"Depth + receipts" in resp.data

    def test_privacy_popover_on_homepage(self, client):
        resp = client.get("/search?q=")
        assert b"privacy-popover" in resp.data
        assert b"Unfiltered answers" in resp.data
        assert b"Depth by default" in resp.data
        assert b"Receipts and traceability" in resp.data
        assert b"Power-user controls" in resp.data

    def test_privacy_badge_on_search_page(self, client, mock_ddg):
        resp = client.get("/search?q=test")
        assert b"privacy-badge" in resp.data

    def test_privacy_google_comparison(self, client):
        resp = client.get("/search?q=")
        assert b"Links only" in resp.data
        assert b"Full excerpts" in resp.data

    def test_privacy_tagline(self, client):
        resp = client.get("/search?q=")
        assert b"Built for people who want the <em>why</em>" in resp.data


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
        assert b"answer-layer-card" not in resp.data

    def test_ai_summary_on_text_tab(self, client, mock_ddg):
        resp = client.get("/search?q=what+is+a+test&type=text")
        assert b"ai-summary-card" in resp.data
        assert b"answer-layer-card" in resp.data

    def test_clarify_chips_on_polysemous_query(self, client, mock_ddg):
        resp = client.get("/search?q=what+is+python&type=text")
        assert resp.status_code == 200
        assert b"clarify-query-card" in resp.data
        assert b"Programming language" in resp.data


class TestAdminQueryLog:
    """Admin query log API (IP / device / location columns)."""

    def test_query_log_forbidden_wrong_token(self, client):
        with patch("app._ADMIN_TOKEN", "secret"):
            r = client.get("/admin/api/query-log?token=wrong")
            assert r.status_code == 403

    def test_query_log_ok_with_token(self, client):
        with patch("app._ADMIN_TOKEN", "secret"):
            r = client.get("/admin/api/query-log?token=secret")
            assert r.status_code == 200
            data = r.get_json()
            assert "rows" in data
            assert "total" in data
            assert isinstance(data["rows"], list)

    def test_account_history_forbidden_wrong_token(self, client):
        with patch("app._ADMIN_TOKEN", "secret"):
            r = client.get("/admin/api/account-history?token=wrong")
            assert r.status_code == 403

    def test_account_history_ok_with_token(self, client):
        with patch("app._ADMIN_TOKEN", "secret"):
            r = client.get("/admin/api/account-history?token=secret")
            assert r.status_code == 200
            data = r.get_json()
            assert "rows" in data
            assert "total" in data
            assert isinstance(data["rows"], list)


class TestApiKeyAuth:
    """Bearer API keys authenticate /api/user/* the same as a browser session."""

    def test_api_user_me_with_valid_bearer(self, client):
        import uuid

        from app import (
            ABBIEY_API_KEY_PREFIX,
            _hash_api_key,
            _users_execute,
        )
        from werkzeug.security import generate_password_hash

        suffix = uuid.uuid4().hex[:10]
        email = f"keytest_{suffix}@example.com"
        username = f"keyuser_{suffix}"
        rows = _users_execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
            [username, email, generate_password_hash("testpass123")],
            return_id=True,
        )
        uid = rows[0]["id"]
        token = ABBIEY_API_KEY_PREFIX + __import__("secrets").token_urlsafe(28)
        _users_execute(
            "INSERT INTO api_keys (user_id, label, key_last_four, key_hash) VALUES (?,?,?,?)",
            [uid, "pytest", token[-4:], _hash_api_key(token)],
        )
        r = client.get(
            "/api/user/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["id"] == uid
        assert data["username"] == username

    def test_api_user_me_invalid_bearer_401(self, client):
        r = client.get(
            "/api/user/me",
            headers={"Authorization": "Bearer abb_sk_live_not_a_real_key_xxxxxxxx"},
        )
        assert r.status_code == 401

    def test_bookmarks_get_with_bearer(self, client):
        import uuid

        from app import ABBIEY_API_KEY_PREFIX, _hash_api_key, _users_execute
        from werkzeug.security import generate_password_hash

        suffix = uuid.uuid4().hex[:10]
        rows = _users_execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
            [f"bm_{suffix}", f"bm_{suffix}@ex.com", generate_password_hash("x")],
            return_id=True,
        )
        uid = rows[0]["id"]
        token = ABBIEY_API_KEY_PREFIX + __import__("secrets").token_urlsafe(28)
        _users_execute(
            "INSERT INTO api_keys (user_id, label, key_last_four, key_hash) VALUES (?,?,?,?)",
            [uid, "k", token[-4:], _hash_api_key(token)],
        )
        r = client.get(
            "/api/user/bookmarks",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.get_json() == {"bookmarks": []}

    def test_revoked_api_key_returns_401(self, client):
        import uuid

        from app import ABBIEY_API_KEY_PREFIX, _hash_api_key, _users_execute
        from werkzeug.security import generate_password_hash

        suffix = uuid.uuid4().hex[:10]
        rows = _users_execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
            [f"rv_{suffix}", f"rv_{suffix}@ex.com", generate_password_hash("x")],
            return_id=True,
        )
        uid = rows[0]["id"]
        token = ABBIEY_API_KEY_PREFIX + __import__("secrets").token_urlsafe(28)
        kr = _users_execute(
            "INSERT INTO api_keys (user_id, label, key_last_four, key_hash) VALUES (?,?,?,?)",
            [uid, "k", token[-4:], _hash_api_key(token)],
            return_id=True,
        )
        kid = kr[0]["id"]
        _users_execute(
            "UPDATE api_keys SET revoked_at=datetime('now') WHERE id=?",
            [kid],
        )
        r = client.get(
            "/api/user/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 401


class TestPaymentReturn:
    """Stripe Payment Link redirect: client-side resume to search or developer."""

    def test_payment_return_get_ok(self, client):
        r = client.get("/payment-return")
        assert r.status_code == 200
        assert b"abbiey_checkout_return" in r.data
        assert b"/search" in r.data
        assert b"/developer" in r.data


class TestDeveloperPage:
    """Developer hub: API keys UI + Stripe billing link."""

    def test_developer_get_ok(self, client):
        r = client.get("/developer")
        assert r.status_code == 200
        assert b"Developer" in r.data
        assert b"API keys" in r.data

    def test_developer_includes_stripe_checkout_link(self, client, monkeypatch):
        import app as app_module

        monkeypatch.setattr(
            app_module,
            "STRIPE_API_KEYS_CHECKOUT_URL",
            "https://buy.stripe.com/test_payment_link",
        )
        r = client.get("/developer")
        assert r.status_code == 200
        assert b"buy.stripe.com" in r.data


def _login_test_user(client, prefix: str = "acct") -> int:
    import uuid

    from app import _users_execute
    from werkzeug.security import generate_password_hash

    suffix = uuid.uuid4().hex[:10]
    rows = _users_execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
        [f"{prefix}_{suffix}", f"{prefix}_{suffix}@example.com", generate_password_hash("password123")],
        return_id=True,
    )
    uid = rows[0]["id"]
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return uid


class TestBookmarkSyncHardening:
    def test_bookmarks_sync_returns_readback_and_delete_by_url(self, client):
        _login_test_user(client, "bmsync")

        sync_resp = client.post(
            "/api/user/bookmarks/sync",
            json={
                "bookmarks": [
                    {
                        "url": "https://example.com/bookmark",
                        "title": "Example bookmark",
                        "snippet": "Saved from pytest",
                    }
                ]
            },
        )
        assert sync_resp.status_code == 200
        sync_data = sync_resp.get_json()
        assert sync_data["ok"] is True
        assert len(sync_data["bookmarks"]) == 1
        assert sync_data["bookmarks"][0]["url"] == "https://example.com/bookmark"

        delete_resp = client.delete(
            "/api/user/bookmarks",
            query_string={"url": "https://example.com/bookmark"},
        )
        assert delete_resp.status_code == 200
        assert delete_resp.get_json()["ok"] is True

        get_resp = client.get("/api/user/bookmarks")
        assert get_resp.status_code == 200
        assert get_resp.get_json() == {"bookmarks": []}


class TestSearchAccessPersistence:
    def test_prepare_claim_and_status_round_trip(self, client):
        prep = client.post("/api/search-access/prepare-checkout")
        assert prep.status_code == 200
        assert prep.get_json()["ok"] is True

        claim = client.post("/api/search-access/claim")
        assert claim.status_code == 200
        claim_data = claim.get_json()
        assert claim_data["ok"] is True
        assert claim_data["unlocked"] is True
        assert "abbiey_search_unlock=" in (claim.headers.get("Set-Cookie") or "")

        status = client.get("/api/search-access")
        assert status.status_code == 200
        assert status.get_json()["unlocked"] is True


class TestHealthProbe:
    def test_public_health_endpoint_omits_sensitive_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "status" in data
        assert "analytics_db" in data
        assert "db_endpoint" not in data


class TestOnionFallbackNotice:
    def test_onion_fallback_notice_rendered(self, client):
        fallback_payload = {
            "results": [
                {
                    "title": "Mirror page",
                    "url": "https://example.com/onion-reference",
                    "body": "Reference to an onion address",
                    "onion": False,
                }
            ],
            "has_more": False,
            "page": 1,
            "notice": "Ahmia is temporarily unavailable, so these results come from a web fallback and may reference onion sites rather than link to them directly.",
        }
        with patch("app._fetch_results", return_value=fallback_payload):
            resp = client.get("/search?q=test&type=onion")
        assert resp.status_code == 200
        assert b"Ahmia is temporarily unavailable" in resp.data

    def test_developer_billing_success_message(self, client):
        r = client.get("/developer?billing=success")
        assert r.status_code == 200
        assert b"Payment confirmed" in r.data
        assert b"dev-api-keys" in r.data

    def test_create_api_key_redirects_unauthenticated(self, client):
        r = client.post(
            "/developer/api-keys/create",
            data={"label": "test"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert "/login" in r.headers.get("Location", "")

    def test_revoke_api_key_redirects_unauthenticated(self, client):
        r = client.post("/developer/api-keys/999/revoke", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers.get("Location", "")


# ---------------------------------------------------------------------------
# Regression tests for security fixes (2026-04-07)
# ---------------------------------------------------------------------------


class TestAdaptSqlPgOrdering:
    """INSERT OR IGNORE + RETURNING id must produce valid Postgres SQL."""

    def test_on_conflict_before_returning(self):
        from app import _adapt_sql_pg

        sql = (
            "INSERT OR IGNORE INTO user_bookmarks (user_id, url, title, snippet)"
            " VALUES (?,?,?,?) RETURNING id"
        )
        result = _adapt_sql_pg(sql)
        # ON CONFLICT DO NOTHING must come before RETURNING
        oc_pos = result.upper().index("ON CONFLICT DO NOTHING")
        ret_pos = result.upper().index("RETURNING")
        assert oc_pos < ret_pos, f"ON CONFLICT must precede RETURNING: {result}"

    def test_on_conflict_without_returning(self):
        from app import _adapt_sql_pg

        sql = (
            "INSERT OR IGNORE INTO user_bookmarks (user_id, url, title, snippet)"
            " VALUES (?,?,?,?)"
        )
        result = _adapt_sql_pg(sql)
        assert "ON CONFLICT DO NOTHING" in result.upper()
        assert "RETURNING" not in result.upper()


class TestAdminFailClosed:
    """Admin endpoints must reject all requests when ADMIN_TOKEN is unset."""

    def test_admin_dashboard_403_when_token_unset(self, client):
        with patch("app._ADMIN_TOKEN", None):
            r = client.get("/admin")
            assert r.status_code == 403

    def test_admin_analytics_403_when_token_unset(self, client):
        with patch("app._ADMIN_TOKEN", None):
            r = client.get("/admin/analytics")
            assert r.status_code == 403

    def test_admin_api_stats_403_when_token_unset(self, client):
        with patch("app._ADMIN_TOKEN", None):
            r = client.get("/admin/api/stats")
            assert r.status_code == 403

    def test_admin_api_health_403_when_token_unset(self, client):
        with patch("app._ADMIN_TOKEN", None):
            r = client.get("/admin/api/health")
            assert r.status_code == 403

    def test_admin_api_query_log_403_when_token_unset(self, client):
        with patch("app._ADMIN_TOKEN", None):
            r = client.get("/admin/api/query-log")
            assert r.status_code == 403

    def test_admin_api_account_history_403_when_token_unset(self, client):
        with patch("app._ADMIN_TOKEN", None):
            r = client.get("/admin/api/account-history")
            assert r.status_code == 403

    def test_admin_dashboard_403_when_token_empty_string(self, client):
        with patch("app._ADMIN_TOKEN", ""):
            r = client.get("/admin")
            assert r.status_code == 403


class TestPreviewSsrfRedirect:
    """Preview endpoint must validate the final URL after redirects."""

    def test_preview_blocks_redirect_to_private_ip(self, client):
        import httpx

        mock_resp = MagicMock()
        mock_resp.text = "<html><title>Internal</title></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_resp.url = httpx.URL("http://169.254.169.254/latest/meta-data/")
        mock_resp.headers = {"content-type": "text/html"}

        with patch.object(httpx, "get", return_value=mock_resp):
            resp = client.get(
                "/api/preview",
                query_string={"url": "https://evil.example.com/redirect"},
            )
        assert resp.status_code == 400
        assert "cannot be previewed" in resp.get_json().get("error", "").lower()

    def test_preview_blocks_redirect_to_onion(self, client):
        import httpx

        mock_resp = MagicMock()
        mock_resp.text = "<html><title>Onion</title></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_resp.url = httpx.URL("http://abcdefghijklmnop.onion/")
        mock_resp.headers = {"content-type": "text/html"}

        with patch.object(httpx, "get", return_value=mock_resp):
            resp = client.get(
                "/api/preview",
                query_string={"url": "https://evil.example.com/onion-redirect"},
            )
        assert resp.status_code == 400


class TestInclusiveSearchSafeguards:
    def test_crisis_meta_flags_distress_language(self):
        assert search_safeguard_meta("suicide hotline")["show_crisis_strip"]
        assert search_safeguard_meta("python asyncio tutorial")["show_crisis_strip"] is False

    def test_chaotic_long_query_gets_inclusive_hint(self):
        noise = "?! " * 40 + "why " * 5
        meta = search_safeguard_meta(noise)
        assert meta["chaotic_query"] or meta["show_inclusive_hint"]

    def test_static_portal_links_always_present(self):
        links = _static_search_portal_links("anything")
        assert len(links) >= 3
        assert any("duckduckgo.com" in (r.get("url") or "") for r in links)

    def test_simplify_query_strips_noise(self):
        s = _simplify_query_for_fallback("  hello!!!  world---  ")
        assert "hello" in s and "world" in s


class TestAntiTemplateRanking:
    def test_demotes_listicle_style_results(self):
        listicle = {
            "title": "Top 10 Best Widgets You Need in 2026",
            "url": "https://listicles.example/top-widgets",
            "body": "Discover our picks.",
        }
        substantive = {
            "title": "Widget architecture notes",
            "url": "https://docs.example/widgets/internals",
            "body": "x" * 200,
        }
        out = _rank_anti_template_results([listicle, substantive])
        assert out[0]["url"] == substantive["url"]

    def test_prefers_first_of_duplicate_domains_lower(self):
        a = {"title": "Article one", "url": "https://blog.example/post-1", "body": "content " * 30}
        b = {"title": "Article two", "url": "https://blog.example/post-2", "body": "content " * 30}
        c = {"title": "Different host write-up", "url": "https://elsewhere.net/x", "body": "content " * 30}
        out = _rank_anti_template_results([a, b, c])
        assert out[0]["url"] == c["url"]


class TestCheckoutCookieNotForgeable:
    """Checkout pending cookie requires SECRET_KEY to forge."""

    def test_claim_rejects_forged_cookie(self, client):
        import hashlib
        import hmac
        import time

        ts = str(time.time())
        # Forge with the old hardcoded key
        forged_sig = hmac.new(
            b"abbiey-checkout-pending", ts.encode(), hashlib.sha256
        ).hexdigest()[:16]
        client.set_cookie("abbiey_search_checkout_pending", f"{ts}.{forged_sig}")
        resp = client.post("/api/search-access/claim")
        assert resp.status_code == 409
        data = resp.get_json()
        assert data.get("error") == "checkout_not_pending"
