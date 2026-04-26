"""Tests for reverse-image lookup helpers and API."""

import io
from unittest.mock import patch

import app as app_module
import reverse_image_storage as _ris
from reverse_image import (
    _reverse_hits_from_openwebninja_json,
    fetch_reverse_hits_for_image_url,
    parse_bing_reverse_html,
    validate_client_image_url,
)


def test_validate_client_image_url_https_only():
    ok, _ = validate_client_image_url("https://example.com/a.jpg")
    assert ok
    ok2, _ = validate_client_image_url("http://example.com/a.jpg")
    assert not ok2


def test_sniff_image_magic_avif_ftyp():
    blob = b"\x00\x00\x00\x20ftypavif\x00\x00\x00\x00" + b"\x00" * 16
    assert app_module._sniff_image_magic(blob) == "image/avif"


def test_api_reverse_image_multipart_localhost_without_storage_fallback_errors(client, monkeypatch):
    """With no Supabase creds *and* no SITE_URL, uploads 422 with an explicit message."""
    monkeypatch.delenv("OPENWEBNINJA_API_KEY", raising=False)
    monkeypatch.delenv("OPENWEBNINJA_REVERSE_IMAGE_KEY", raising=False)
    monkeypatch.delenv("SITE_URL", raising=False)
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    with patch.object(_ris, "put_object", return_value=None):
        resp = client.post(
            "/api/reverse-image",
            data={"image": (io.BytesIO(jpeg), "photo.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 422
    assert resp.get_json().get("error") == "upload_needs_public_https"


def test_api_reverse_image_multipart_uses_supabase_storage_without_site_url(client):
    """When Supabase Storage is wired up, uploads succeed even with no SITE_URL."""
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    fake_hits = [
        {
            "title": "Match",
            "url": "https://page.example/x",
            "image": "https://img.example/x.jpg",
            "thumbnail": "https://img.example/x.jpg",
            "source": "page.example",
            "body": "caption",
        }
    ]
    handle = _ris.StoredObject(bucket="reverse-image-uploads", path="abc.jpg")
    signed = "https://project.supabase.co/storage/v1/object/sign/reverse-image-uploads/abc.jpg?token=xyz"
    deletes: list[_ris.StoredObject] = []

    def _fake_put(raw, mime):
        assert raw.startswith(b"\xff\xd8\xff")
        return signed, handle

    def _fake_delete(h):
        deletes.append(h)

    with patch.object(_ris, "put_object", side_effect=_fake_put), \
         patch.object(_ris, "delete_object", side_effect=_fake_delete), \
         patch("app.fetch_reverse_hits_for_image_url", return_value=fake_hits):
        resp = client.post(
            "/api/reverse-image",
            data={"image": (io.BytesIO(jpeg), "photo.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("ok") is True
    assert "img_rev_key=" in data.get("redirect", "")
    assert deletes == [handle]


def test_reverse_image_storage_put_object_without_env_returns_none(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    assert _ris.put_object(b"\xff\xd8\xff\xe0", "image/jpeg") is None
    assert _ris.is_configured() is False


def test_openwebninja_response_maps_to_hits():
    out = _reverse_hits_from_openwebninja_json(
        {
            "status": "OK",
            "data": [
                {
                    "title": "Page title",
                    "link": "https://example.com/p",
                    "domain": "example.com",
                    "image": "https://thumb.example/t.jpg",
                }
            ],
        }
    )
    assert len(out) == 1
    assert out[0]["url"] == "https://example.com/p"
    assert out[0]["image"] == "https://thumb.example/t.jpg"
    assert out[0]["source"] == "example.com"


def test_fetch_reverse_uses_openwebninja_when_key_set(monkeypatch):
    """When OPENWEBNINJA_API_KEY is set, the OpenWeb Ninja path is used (not Bing)."""
    monkeypatch.setenv("OPENWEBNINJA_API_KEY", "ak_testkey")

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "status": "OK",
                "data": [
                    {
                        "title": "From API",
                        "link": "https://page.example/hi",
                        "domain": "page.example",
                        "image": "https://img.example/x.png",
                    }
                ],
            }

    class FakeClient:
        def get(self, *a, **k):
            return FakeResp()

    hits = fetch_reverse_hits_for_image_url(
        "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg",
        client=FakeClient(),
    )
    assert len(hits) == 1
    assert hits[0]["url"] == "https://page.example/hi"
    assert hits[0]["title"] == "From API"


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
