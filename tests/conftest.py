"""Pytest fixtures for FreeSearch test suite."""

import pytest
from unittest.mock import patch, MagicMock

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app as flask_app, limiter


@pytest.fixture
def app():
    """Flask app configured for testing."""
    flask_app.config["TESTING"] = True
    limiter.enabled = False  # Disable rate limiting in tests
    yield flask_app
    limiter.enabled = True


@pytest.fixture
def client(app):
    """Flask test client."""
    with app.test_client() as c:
        yield c


@pytest.fixture
def mock_ddg():
    """Mock DDGS to avoid real network calls."""
    with patch("app.DDGS") as mock:
        instance = MagicMock()
        mock.return_value = instance

        # Default: return some text results
        instance.text.return_value = [
            {"title": "Result 1", "href": "https://example.com/1", "body": "Body 1"},
            {"title": "Result 2", "href": "https://example.com/2", "body": "Body 2"},
        ]
        instance.images.return_value = [
            {"title": "Img 1", "url": "https://example.com/img1", "image": "https://example.com/img1.jpg",
             "thumbnail": "https://example.com/thumb1.jpg", "source": "Example"},
        ]
        instance.news.return_value = [
            {"title": "News 1", "url": "https://news.example.com/1", "body": "News body",
             "source": "Example News", "date": "2026-01-01"},
        ]
        instance.videos.return_value = [
            {"title": "Video 1", "content": "https://video.example.com/1",
             "description": "Video desc", "publisher": "VidHost",
             "images": {"large": "https://example.com/vthumb.jpg"}, "duration": "5:30"},
        ]
        yield instance


@pytest.fixture
def mock_chat():
    """Mock _ddg_chat to avoid real DuckDuckGo AI Chat calls."""
    with patch("app._ddg_chat") as mock:
        mock.return_value = "This is a mock AI response based on search results."
        yield mock


@pytest.fixture
def mock_httpx():
    """Mock httpx client to avoid real network calls."""
    with patch("app._get_http") as mock:
        http = MagicMock()
        mock.return_value = http

        # Default: return empty response for SearXNG
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"results": []}
        resp.text = ""
        http.get.return_value = resp

        yield http


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the result cache before each test."""
    from app import _cache, _cache_lock
    with _cache_lock:
        _cache.clear()
    yield
    with _cache_lock:
        _cache.clear()
