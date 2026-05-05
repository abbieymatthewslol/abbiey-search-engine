"""Hotel finder blueprint and hotel-related query handling."""

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

