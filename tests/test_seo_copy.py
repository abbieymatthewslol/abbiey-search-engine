"""SEO copy and search mode title helpers."""

from seo_copy import get_seo, json_ld_webapp, manifest_description
from search_routing import search_mode_title_suffix


def test_get_seo_known_page():
    seo = get_seo("breach_check")
    assert "breach" in seo["title"].lower()
    assert seo["keywords"]


def test_get_seo_unknown_falls_back():
    seo = get_seo("not-a-real-page")
    assert seo["title"]
    assert seo["description"]


def test_json_ld_webapp_search_action():
    data = json_ld_webapp("https://abbieysearch.com")
    assert data["@type"] == "WebApplication"
    assert "OSINT" in data["description"] or "entity" in data["description"].lower()
    assert data["potentialAction"]["@type"] == "SearchAction"


def test_manifest_description_mentions_osint():
    assert "OSINT" in manifest_description() or "entity" in manifest_description().lower()


def test_search_mode_title_suffix_onion():
    assert search_mode_title_suffix("onion") == ".onion index search"


def test_search_mode_title_suffix_people():
    assert "OSINT" in search_mode_title_suffix("people")
