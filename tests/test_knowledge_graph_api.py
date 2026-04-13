"""Tests for GET /api/knowledge-graph."""

from unittest.mock import patch


def test_knowledge_graph_empty_query(client):
    resp = client.get("/api/knowledge-graph?q=")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["wikipedia"] is None
    assert data["related"] == []
    assert data["topics"] == []
    assert data["categories"] == []


class _FakeAcResp:
    def json(self):
        return [None, ["Python tutorial", "Python 3"]]


@patch("app.httpx.get", return_value=_FakeAcResp())
@patch("app._wikipedia_category_labels", return_value=["Science"])
@patch("app._wikidata_topic_labels", return_value=["Topic A"])
@patch(
    "app._try_knowledge_panel",
    return_value={
        "title": "Python",
        "extract": "Python is a programming language." * 5,
        "image_url": "",
        "page_url": "https://en.wikipedia.org/wiki/Python",
    },
)
def test_knowledge_graph_returns_payload(_mock_wiki, _mock_wd, _mock_cats, _mock_http, client):
    resp = client.get("/api/knowledge-graph?q=Python")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["wikipedia"]["title"] == "Python"
    assert "Python is" in data["wikipedia"]["extract"]
    assert data["topics"] == ["Topic A"]
    assert data["categories"] == ["Science"]
    assert isinstance(data["related"], list)
