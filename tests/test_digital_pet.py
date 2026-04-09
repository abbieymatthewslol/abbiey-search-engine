"""Digital animal XP, species API, and pages."""

import uuid

import pytest
from werkzeug.security import generate_password_hash

import digital_pet as dp


def _login_test_user(client, prefix: str = "pet") -> int:
    from app import _users_execute

    suffix = uuid.uuid4().hex[:10]
    rows = _users_execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?,?,?)",
        [f"{prefix}_{suffix}", f"{prefix}_{suffix}@example.com", generate_password_hash("password123")],
        return_id=True,
    )
    uid = rows[0]["id"]
    with client.session_transaction() as sess:
        sess["user_id"] = uid
    return uid


def test_stage_and_level_helpers():
    assert dp.stage_from_xp(0) == 0
    assert dp.stage_from_xp(29) == 0
    assert dp.stage_from_xp(30) == 1
    assert dp.stage_from_xp(250) == 3
    assert dp.level_from_xp(0) == 1
    assert dp.level_from_xp(100) >= 2


def test_tier_percentiles():
    assert dp.tier_from_percentile_rank(0.0) == "platinum"
    assert dp.tier_from_percentile_rank(0.03) == "gold"
    assert dp.tier_from_percentile_rank(0.15) == "silver"
    assert dp.tier_from_percentile_rank(0.40) == "bronze"
    assert dp.tier_from_percentile_rank(0.99) == "novice"


def test_pet_page_requires_login(client):
    r = client.get("/pet", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in (r.headers.get("Location") or "")


def test_pet_page_and_species_api(client):
    _login_test_user(client, "petuser")
    r = client.get("/pet")
    assert r.status_code == 200
    assert b"Digital animal" in r.data
    assert b"pet-species-grid" in r.data

    me = client.get("/api/pet/me")
    assert me.status_code == 200
    pet = me.get_json().get("pet") or {}
    assert pet.get("species") == "hummingbird"
    assert pet.get("xp_total") == 0

    ch = client.post("/api/pet/species", json={"species": "dolphin"})
    assert ch.status_code == 200
    assert ch.get_json().get("ok") is True
    assert ch.get_json()["pet"]["species"] == "dolphin"


def test_bookmark_awards_xp_once(client):
    _login_test_user(client, "petbm")
    r1 = client.post(
        "/api/user/bookmarks",
        json={"url": "https://example.com/pet-xp", "title": "T", "snippet": ""},
    )
    assert r1.status_code == 201
    me = client.get("/api/pet/me").get_json()["pet"]
    assert me["xp_total"] >= 3

    r2 = client.post(
        "/api/user/bookmarks",
        json={"url": "https://example.com/pet-xp", "title": "T2", "snippet": ""},
    )
    assert r2.status_code == 201
    xp2 = client.get("/api/pet/me").get_json()["pet"]["xp_total"]
    assert xp2 == me["xp_total"]


def test_leaderboard_renders(client):
    r = client.get("/pet/leaderboard")
    assert r.status_code == 200
    assert b"Leaderboard" in r.data
