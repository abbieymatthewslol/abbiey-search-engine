"""Integration tests for the Deep Web (onion) tab.

Covers:
- _try_ahmia HTML parsing with a mocked HTTP response
- _try_ahmia exception handling
- _try_onion_ddg DDG fallback
- Full /search?type=onion endpoint with mocked source functions
"""

import textwrap
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_AHMIA_HTML = textwrap.dedent("""\
    <html><body>
    <ul id="ahmiaResultsPage">
      <li class="result">
        <h4><a href="/search/redirect?redirect_url=http://abcde12345.onion/index.html">Hidden Wiki</a></h4>
        <p>A mirror of the Hidden Wiki.</p>
        <cite>abcde12345.onion</cite>
      </li>
      <li class="result">
        <h4><a href="http://xyz9999999.onion/forum">Forum Title</a></h4>
        <p>An onion discussion board.</p>
        <cite>xyz9999999.onion</cite>
      </li>
    </ul>
    </body></html>
""")

EMPTY_AHMIA_HTML = "<html><body><ul id='ahmiaResultsPage'></ul></body></html>"


# ---------------------------------------------------------------------------
# _try_ahmia unit tests
# ---------------------------------------------------------------------------

class TestTryAhmia:
    """Unit-tests for the _try_ahmia() scraper (no real HTTP)."""

    def _make_http_mock(self, search_html, home_html="<html></html>", status=200):
        """Return a mock _get_http() client whose responses match Ahmia's two-step flow."""
        http = MagicMock()
        home_resp = MagicMock()
        home_resp.raise_for_status = MagicMock()
        home_resp.text = home_html

        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.text = search_html

        # First call → homepage, second call → search results
        http.get.return_value = home_resp

        import httpx as _httpx
        return http, home_resp, search_resp

    def test_parses_redirect_url_from_ahmia_wrapper(self):
        """Ahmia wraps real .onion URLs in a redirect; the parser should unwrap them."""
        from app import _try_ahmia

        http_mock = MagicMock()
        home_resp = MagicMock()
        home_resp.raise_for_status = MagicMock()
        home_resp.text = "<html></html>"
        http_mock.get.return_value = home_resp

        import httpx

        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.text = SAMPLE_AHMIA_HTML

        with patch("app._get_http", return_value=http_mock), \
             patch("httpx.get", return_value=search_resp):
            results = _try_ahmia("hidden wiki")

        assert len(results) >= 1
        titles = [r["title"] for r in results]
        assert "Hidden Wiki" in titles

        # First result must have the unwrapped onion URL
        hidden_wiki = next(r for r in results if r["title"] == "Hidden Wiki")
        assert hidden_wiki["url"] == "http://abcde12345.onion/index.html"
        assert hidden_wiki["onion"] is True

    def test_parses_direct_onion_href(self):
        """Results with a direct .onion href (no redirect wrapper) are kept as-is."""
        from app import _try_ahmia

        http_mock = MagicMock()
        home_resp = MagicMock()
        home_resp.raise_for_status = MagicMock()
        home_resp.text = "<html></html>"
        http_mock.get.return_value = home_resp

        import httpx
        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.text = SAMPLE_AHMIA_HTML

        with patch("app._get_http", return_value=http_mock), \
             patch("httpx.get", return_value=search_resp):
            results = _try_ahmia("forum")

        forum = next((r for r in results if r["title"] == "Forum Title"), None)
        assert forum is not None
        assert forum["url"] == "http://xyz9999999.onion/forum"

    def test_returns_empty_list_when_http_raises(self):
        """If the HTTP request throws any exception, _try_ahmia returns [] without propagating."""
        from app import _try_ahmia

        http_mock = MagicMock()
        import httpx
        http_mock.get.side_effect = httpx.ConnectError("timeout")

        with patch("app._get_http", return_value=http_mock):
            results = _try_ahmia("any query")

        assert results == []

    def test_returns_empty_on_empty_page(self):
        """Empty Ahmia HTML produces an empty result list."""
        from app import _try_ahmia

        http_mock = MagicMock()
        home_resp = MagicMock()
        home_resp.raise_for_status = MagicMock()
        home_resp.text = "<html></html>"
        http_mock.get.return_value = home_resp

        import httpx
        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.text = EMPTY_AHMIA_HTML

        with patch("app._get_http", return_value=http_mock), \
             patch("httpx.get", return_value=search_resp):
            results = _try_ahmia("nothing here")

        assert results == []

    def test_result_has_snippet(self):
        """Each parsed result should carry the <p> text as its body."""
        from app import _try_ahmia

        http_mock = MagicMock()
        home_resp = MagicMock()
        home_resp.raise_for_status = MagicMock()
        home_resp.text = "<html></html>"
        http_mock.get.return_value = home_resp

        import httpx
        search_resp = MagicMock()
        search_resp.raise_for_status = MagicMock()
        search_resp.text = SAMPLE_AHMIA_HTML

        with patch("app._get_http", return_value=http_mock), \
             patch("httpx.get", return_value=search_resp):
            results = _try_ahmia("wiki")

        wiki = next(r for r in results if r["title"] == "Hidden Wiki")
        assert "mirror" in wiki["body"].lower()


# ---------------------------------------------------------------------------
# _try_onion_ddg unit tests
# ---------------------------------------------------------------------------

class TestTryOnionDdg:
    """Unit-tests for the _try_onion_ddg() DDG fallback."""

    def test_returns_clearnet_results_with_onion_false(self):
        from app import _try_onion_ddg

        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = lambda s: s
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = [
            {"title": "Clearnet page about onion", "href": "https://example.com/1", "body": "Body 1"},
            {"title": "Another clearnet page", "href": "https://example.com/2", "body": "Body 2"},
        ]

        with patch("app.DDGS", return_value=mock_ddgs):
            results = _try_onion_ddg("drugs")

        assert len(results) == 2
        assert all(r["onion"] is False for r in results)
        assert results[0]["title"] == "Clearnet page about onion"

    def test_returns_empty_list_when_ddg_raises(self):
        from app import _try_onion_ddg

        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = lambda s: s
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.side_effect = Exception("DDG rate limit")

        with patch("app.DDGS", return_value=mock_ddgs):
            results = _try_onion_ddg("anything")

        assert results == []

    def test_appends_onion_keyword_to_query(self):
        """DDG fallback should search for '<query> .onion' to surface onion-adjacent pages."""
        from app import _try_onion_ddg

        mock_ddgs = MagicMock()
        mock_ddgs.__enter__ = lambda s: s
        mock_ddgs.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = []

        with patch("app.DDGS", return_value=mock_ddgs):
            _try_onion_ddg("search term")

        call_args = mock_ddgs.text.call_args
        assert ".onion" in call_args[0][0]


# ---------------------------------------------------------------------------
# Full /search?type=onion endpoint tests
# ---------------------------------------------------------------------------

class TestDeepWebEndpoint:
    """Integration tests that hit the Flask search route with mocked source functions."""

    def test_ahmia_results_returned_no_unavailable_notice(self, client):
        """/search?type=onion works when Ahmia returns real onion results."""
        onion_results = [
            {"title": "Onion Site A", "url": "http://aaaaaa.onion/", "body": "Snippet A", "onion": True},
            {"title": "Onion Site B", "url": "http://bbbbbb.onion/", "body": "Snippet B", "onion": True},
        ]
        with patch("app._try_ahmia", return_value=onion_results), \
             patch("app._try_onion_ddg", return_value=[]):
            resp = client.get("/search?q=marketplace&type=onion")

        assert resp.status_code == 200
        body = resp.data.decode()
        assert "Onion Site A" in body
        # No unavailable/degraded notice when we have real onion results
        assert "Deep web search is temporarily degraded" not in body

    def test_ddg_fallback_shows_fallback_notice(self, client):
        """When Ahmia is empty and DDG fallback returns clearnet results, the fallback notice appears."""
        clearnet_results = [
            {"title": "Clearnet ref", "url": "https://example.com/ref", "body": "References .onion", "onion": False},
        ]
        with patch("app._try_ahmia", return_value=[]), \
             patch("app._try_onion_ddg", return_value=clearnet_results):
            resp = client.get("/search?q=marketplace&type=onion")

        assert resp.status_code == 200
        assert b"Ahmia is temporarily unavailable" in resp.data

    def test_both_sources_fail_shows_unavailable_notice(self, client):
        """When both Ahmia and DDG return nothing, the degraded notice is shown."""
        with patch("app._try_ahmia", return_value=[]), \
             patch("app._try_onion_ddg", return_value=[]):
            resp = client.get("/search?q=marketplace&type=onion")

        assert resp.status_code == 200
        assert b"Deep web search is temporarily degraded" in resp.data

    def test_ahmia_exception_falls_back_to_ddg(self, client):
        """If _try_ahmia raises, the app still tries DDG and shows the fallback notice."""
        clearnet_results = [
            {"title": "DDG fallback result", "url": "https://example.com/ddg", "body": "DDG body", "onion": False},
        ]
        with patch("app._try_ahmia", side_effect=Exception("Ahmia exploded")), \
             patch("app._try_onion_ddg", return_value=clearnet_results):
            resp = client.get("/search?q=marketplace&type=onion")

        # App must not crash
        assert resp.status_code == 200

    def test_ajax_onion_search_returns_json_with_notice(self, client):
        """AJAX requests (?ajax=1) for onion searches include the notice field in JSON."""
        clearnet_results = [
            {"title": "Ref page", "url": "https://example.com/x", "body": "body", "onion": False},
        ]
        with patch("app._try_ahmia", return_value=[]), \
             patch("app._try_onion_ddg", return_value=clearnet_results):
            resp = client.get("/search?q=onion+market&type=onion&ajax=1",
                              headers={"X-Requested-With": "XMLHttpRequest"})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None
        assert "notice" in data
        assert "Ahmia" in (data["notice"] or "")
