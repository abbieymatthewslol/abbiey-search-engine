from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_tor_agreement_markup_present():
    html = (REPO_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'id="tor-agreement-overlay"' in html
    assert 'id="tor-agreement-title"' in html
    assert 'id="tor-agreement-copy"' in html
    assert 'id="tor-agreement-check"' in html
    assert "Please be aware before using the Tor filter" in html


def test_tor_agreement_styles_present():
    css = (REPO_ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ".tor-agreement-overlay" in css
    assert ".tor-agreement-banner" in css
    assert "body.tor-agreement-active" in css


def test_tor_agreement_script_guards_onion_access():
    js = (REPO_ROOT / "static" / "script.js").read_text(encoding="utf-8")
    assert "function initTorAgreementGate()" in js
    assert "function isTorSearchMode(mode)" in js
    assert "torAgreementGate.ensureAgreement" in js
    assert "searchTypeFromHref(anchor.href)" in js
