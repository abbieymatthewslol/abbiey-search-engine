"""Tests for /api/unfiltered leaderboard + activity (anonymized)."""

import json
import uuid

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_unfiltered_leaderboard_ok(client):
    r = client.get("/api/unfiltered/leaderboard")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert "entries" in data
    assert isinstance(data["entries"], list)


def test_unfiltered_activity_invalid_participant(client):
    r = client.post(
        "/api/unfiltered/activity",
        data=json.dumps({"participant_id": "not-a-uuid"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_unfiltered_activity_roundtrip(client):
    pid = str(uuid.uuid4())
    r = client.post(
        "/api/unfiltered/activity",
        data=json.dumps({"participant_id": pid, "depth": 2, "receipts": 0}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json().get("ok") is True
    lb = client.get("/api/unfiltered/leaderboard")
    assert lb.status_code == 200
    entries = lb.get_json().get("entries") or []
    assert len(entries) >= 1
    assert any(e.get("score", 0) > 0 for e in entries)
