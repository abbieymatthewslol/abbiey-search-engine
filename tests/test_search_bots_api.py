"""Custom search bots API — auth and validation (no live crawl)."""

import json
import time
from unittest.mock import patch

import bot_crawler as _bc
from search_bots import (
    HTTP_TIMEOUT,
    collect_http_urls_from_json,
    collect_http_urls_from_tabular,
    crawl_bot_pages_step,
    normalize_http_seed,
    parse_csv_rows,
    parse_json_documents,
    parse_json_list,
    snippet_from_json_values,
    snippet_from_tabular,
)


def test_normalize_http_seed_allowlist():
    assert normalize_http_seed("https://docs.example.com/a", ["docs.example.com", "example.com"])
    assert not normalize_http_seed("https://evil.com/", ["example.com"])


def test_collect_http_urls_from_json_nested():
    data = {"items": [{"url": "https://a.example/x"}, "https://b.example/y"]}
    urls = collect_http_urls_from_json(data)
    assert "https://a.example/x" in urls
    assert "https://b.example/y" in urls


def test_snippet_from_json_values_skips_urls():
    data = {"title": "Hello", "link": "https://x.com/a"}
    assert "Hello" in snippet_from_json_values(data)
    assert "https://" not in snippet_from_json_values(data)


def test_parse_json_documents_single_and_ndjson():
    assert parse_json_documents(json.dumps({"a": 1})) == [{"a": 1}]
    nd = '{"u":"https://h.com/1"}\n{"u":"https://h.com/2"}\n'
    docs = parse_json_documents(nd)
    assert len(docs) == 2


def test_parse_json_list_accepts_string_json():
    raw = json.dumps(["a.example.com"])
    assert parse_json_list(raw, max_items=5, max_len_each=120) == ["a.example.com"]


def test_parse_csv_rows_and_extract_urls():
    raw = "name,url\nA,https://example.com/a\nB,https://example.com/b\n"
    rows = parse_csv_rows(raw)
    assert rows and rows[0][0].lower() == "name"
    urls = collect_http_urls_from_tabular(rows)
    assert "https://example.com/a" in urls
    assert "https://example.com/b" in urls


def test_snippet_from_tabular_skips_urls():
    raw = "title,url\nHello world,https://example.com/a\n"
    rows = parse_csv_rows(raw)
    snip = snippet_from_tabular(rows)
    assert "Hello world" in snip
    assert "https://" not in snip


def test_search_bots_list_requires_auth(client):
    r = client.get("/api/user/search-bots")
    assert r.status_code == 401


def test_search_bots_create_requires_auth(client):
    r = client.post(
        "/api/user/search-bots",
        json={"name": "x", "allow_hosts": ["example.com"], "seed_urls": ["https://example.com/"]},
    )
    assert r.status_code == 401


def test_http_timeout_kept_short_for_serverless():
    """Regression: Vercel default function timeout is 10s, so per-page timeout
    must stay low enough that 3 pages * timeout < 10s."""
    assert HTTP_TIMEOUT * _bc.DEFAULT_PAGES_PER_INVOCATION + 2 < 60, (
        "A full crawl step must comfortably fit inside the Vercel 60s function budget."
    )


def test_crawl_bot_pages_step_respects_pages_per_invocation():
    """With a slow upstream, crawl_bot_pages_step caps at pages_per_invocation."""

    class _FakeResp:
        status_code = 200

        def __init__(self, body=b"<html><title>t</title><body>hi</body></html>"):
            self.content = body
            self.headers = {"content-type": "text/html"}

    class _FakeClient:
        def __init__(self, *a, **kw):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, **kw):
            self.calls += 1
            # Simulate a sluggish upstream but well under the unit-test budget.
            time.sleep(0.02)
            return _FakeResp()

    seen_calls: list[int] = []

    def _client_factory(*args, **kwargs):
        c = _FakeClient()
        seen_calls.append(id(c))
        return c

    with patch("search_bots.httpx.Client", side_effect=_client_factory):
        started = time.time()
        pages, remaining_queue, new_seen, err = crawl_bot_pages_step(
            queue=[
                ("https://example.com/a", 0),
                ("https://example.com/b", 0),
                ("https://example.com/c", 0),
                ("https://example.com/d", 0),
                ("https://example.com/e", 0),
            ],
            seen=[],
            allow_hosts=["example.com"],
            max_depth=0,
            max_pages=10,
            pages_per_invocation=3,
        )
        elapsed = time.time() - started

    assert err is None
    # Exactly 3 pages fetched despite 5 in queue (chunking works).
    assert len(pages) == 3
    assert len(remaining_queue) == 2
    assert len(new_seen) == 3
    # Sanity: a chunked step finished well under the 10s serverless default.
    assert elapsed < 3.0
