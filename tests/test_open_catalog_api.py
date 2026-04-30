"""GET /api/open-catalog"""

from unittest.mock import patch


def test_open_catalog_api_returns_hits(client):
    fake = [{"title": "Paper", "url": "https://doi.org/10.1/x", "body": "Abstract", "source": "Crossref"}]
    with patch("app.fetch_open_knowledge_hits", return_value=fake):
        r = client.get("/api/open-catalog?q=neutrino")
    assert r.status_code == 200
    data = r.get_json()
    assert data["query"] == "neutrino"
    assert data["count"] == 1
    assert data["results"][0]["url"] == "https://doi.org/10.1/x"


def test_open_catalog_api_400_empty(client):
    r = client.get("/api/open-catalog?q=")
    assert r.status_code == 400
