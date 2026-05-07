"""Hotel finder blueprint and hotel-related query handling."""

from unittest.mock import patch

from entity_parser import detect_entities


def test_hotels_path_returns_200_without_redirect(client):
    resp = client.get("/hotels", follow_redirects=False)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Hotels" in body
    assert "/static/hotels-skyline.png" in body


def test_hotels_plural_normalizes_for_place_category():
    entities = detect_entities("hotels in Paris")
    cats = [e for e in entities if e.type == "place_category"]
    assert cats, "expected plural hotels to normalize to hotel phrase"
    assert cats[0].normalized == "hotel"


def test_hotels_api_search_requires_destination(client):
    resp = client.get("/hotels/api/search", follow_redirects=False)
    assert resp.status_code == 400
    assert resp.is_json
    assert "error" in resp.get_json()


def test_hotels_api_search_includes_cheapest_and_disclaimer(client):
    rows = [
        {
            "title": "Cheap Stay",
            "url": "https://example.com/cheap",
            "snippet": "",
            "source": "example.com",
            "scrape_source": "duckduckgo-html",
            "price_usd": 71.0,
            "price_display": "$71 nightly (~US$71)",
        },
        {
            "title": "Pricier Stay",
            "url": "https://example.com/fancy",
            "snippet": "",
            "source": "example.com",
            "scrape_source": "duckduckgo-html",
            "price_usd": 199.0,
            "price_display": "$199 nightly (~US$199)",
        },
    ]
    meta = {
        "cheapest": rows[0],
        "disclaimer": "Nightly prices are parsed from live search snippets.",
    }
    with patch("hotels_blueprint.search_hotels_with_prices", return_value=(rows, meta)):
        resp = client.get("/hotels/api/search?destination=Lyon", follow_redirects=False)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cheapest"]["price_usd"] == 71.0
    assert data["cheapest"]["title"] == "Cheap Stay"
    assert "parsed from live search" in data["disclaimer"]
    assert len(data["results"]) == 2


def test_min_nightly_price_extracts_from_title():
    from hotels_pricing import _min_nightly_price_usd

    usd, disp = _min_nightly_price_usd("10 Best Town Hotels (From US$78)", "Weekend rates apply.", "booking.com")
    assert usd is not None and usd <= 80
    assert disp and "78" in disp


def test_expand_ddg_ad_domain_uses_booking_host_map():
    from hotels_pricing import _expand_ddg_url, _urls_by_host

    links = [{"name": "Booking.com", "url": "https://www.booking.com/search.html?ss=Testland", "icon": "booking"}]
    hmap = _urls_by_host(links)
    out = _expand_ddg_url("https://duckduckgo.com/y.js?ad_domain=booking.com&ad_type=txad", hmap)
    assert out == "https://www.booking.com/search.html?ss=Testland"

