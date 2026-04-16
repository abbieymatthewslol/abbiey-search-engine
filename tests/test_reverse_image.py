"""Tests for reverse-image lookup helpers and API."""

import io
from unittest.mock import patch

import app as app_module
from reverse_image import parse_bing_reverse_html, validate_client_image_url


def test_validate_client_image_url_https_only():
    ok, _ = validate_client_image_url("https://example.com/a.jpg")
    assert ok
    ok2, _ = validate_client_image_url("http://example.com/a.jpg")
    assert not ok2


def test_sniff_image_magic_avif_ftyp():
    blob = b"\x00\x00\x00\x20ftypavif\x00\x00\x00\x00" + b"\x00" * 16
    assert app_module._sniff_image_magic(blob) == "image/avif"


def test_api_reverse_image_multipart_localhost_needs_site_url(client):
    """Upload path requires a public base URL so Bing can fetch the preview once."""
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    resp = client.post(
        "/api/reverse-image",
        data={"image": (io.BytesIO(jpeg), "photo.jpg")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 422
    assert resp.get_json().get("error") == "upload_needs_public_https"


def test_parse_bing_reverse_html_extracts_rows():
    blob = (
        'purl":"https://example.com/article","murl":"https://cdn.example.com/pic.png",'
        '"turl":"https://ts.bing/x","md5":"a","shkey":"b","t":"https://cdn.example.com/pic.png, Nice cat photo"'
    )
    hits = parse_bing_reverse_html(blob)
    assert len(hits) == 1
    assert hits[0]["url"] == "https://example.com/article"
    assert hits[0]["image"] == "https://cdn.example.com/pic.png"
    assert "Nice cat photo" in hits[0]["body"]


def test_api_reverse_image_missing_url(client):
    resp = client.post("/api/reverse-image", json={})
    assert resp.status_code == 400
    assert resp.get_json().get("error") == "missing_image_url"


def test_api_reverse_image_url_happy_path(client):
    fake_hits = [
        {
            "title": "Example",
            "url": "https://page.example/hi",
            "image": "https://img.example/x.jpg",
            "thumbnail": "https://img.example/x.jpg",
            "source": "page.example",
            "body": "caption text",
        }
    ]
    with patch("app.fetch_reverse_hits_for_image_url", return_value=fake_hits):
        resp = client.post(
            "/api/reverse-image",
            json={"image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg"},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("ok") is True
    assert "type=images" in data.get("redirect", "")
    assert "img_rev_key=" in data.get("redirect", "")


def test_search_images_with_rev_key_serves_cached_hits(client):
    fake_hits = [
        {
            "title": "Cached",
            "url": "https://cached.example/",
            "image": "https://cached.example/i.png",
            "thumbnail": "https://cached.example/i.png",
            "source": "cached.example",
            "body": "desc",
        }
    ]
    tok = "revtesttokentwentyfourcharsxx"
    with app_module._reverse_image_hits_lock:
        app_module._reverse_image_hits_cache[tok] = fake_hits
    try:
        resp = client.get(
            f"/search?q=Visual+matches&type=images&img_rev_key={tok}",
        )
    finally:
        with app_module._reverse_image_hits_lock:
            app_module._reverse_image_hits_cache.pop(tok, None)
    assert resp.status_code == 200
    assert b"Cached" in resp.data
    assert b"desc" in resp.data
