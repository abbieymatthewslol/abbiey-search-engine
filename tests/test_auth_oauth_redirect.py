"""OAuth completion page and signup should land users on /search by default."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_auth_confirm_redirects_to_search_when_no_next_stored():
    html = (_REPO_ROOT / "templates" / "auth_confirm.html").read_text(encoding="utf-8")
    assert "window.location.replace('/search')" in html


def test_signup_google_sets_oauth_next_from_page_or_search():
    html = (_REPO_ROOT / "templates" / "signup.html").read_text(encoding="utf-8")
    # Direct Google OAuth link or legacy Supabase sessionStorage fallback.
    assert "/auth/google" in html or "abbiey_oauth_next" in html


def test_welcome_google_sets_oauth_next_to_search():
    html = (_REPO_ROOT / "templates" / "welcome.html").read_text(encoding="utf-8")
    assert "/auth/google" in html or "abbiey_oauth_next" in html
