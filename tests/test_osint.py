"""Unit tests for OSINT validation and module gating (no live network)."""

from osint.modules import _validate_domain, _validate_ipv4
from osint.service import enrich, parse_enabled_modules


def test_validate_domain_strips_and_lowercases():
    assert _validate_domain("Example.COM.") == "example.com"
    assert _validate_domain("https://Sub.EXAMPLE.co.uk/path") == "sub.example.co.uk"


def test_validate_domain_rejects_junk():
    assert _validate_domain("") is None
    assert _validate_domain("not a domain") is None
    assert _validate_domain("a" * 300) is None


def test_validate_ipv4():
    assert _validate_ipv4("1.1.1.1") == "1.1.1.1"
    assert _validate_ipv4("999.1.1.1") is None


def test_enrich_rejects_bad_entity():
    r = enrich(entity_type="person", value="Jane Doe")
    assert r["ok"] is False
    r2 = enrich(entity_type="domain", value="@@@")
    assert r2["ok"] is False


def test_parse_enabled_modules_default():
    m = parse_enabled_modules()
    assert "dns" in m and "rdap" in m


def test_parse_enabled_modules_subset(monkeypatch):
    monkeypatch.setenv("ABBIEY_OSINT_MODULES", "dns")
    assert parse_enabled_modules() == frozenset({"dns"})
