"""Custom search bots API — auth and validation (no live crawl)."""

import json

from search_bots import (
    collect_http_urls_from_json,
    collect_http_urls_from_tabular,
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
