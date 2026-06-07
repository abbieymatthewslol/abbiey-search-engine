"""Direct Google OAuth 2.0 / OpenID Connect — no Supabase Auth required."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPES = "openid email profile"


def google_oauth_configured() -> bool:
    return bool(_client_id() and _client_secret())


def _client_id() -> str:
    return (os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()


def _client_secret() -> str:
    return (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()


def build_authorize_url(*, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": _client_id(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code(*, code: str, redirect_uri: str) -> dict | None:
    code = (code or "").strip()
    if not code or not google_oauth_configured():
        return None
    try:
        r = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=12.0,
        )
    except Exception:
        logger.exception("google_oauth_token_exchange_failed")
        return None
    if r.status_code != 200:
        logger.info("google_oauth_token_exchange_status=%s", r.status_code)
        return None
    try:
        data = r.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def fetch_userinfo(access_token: str) -> dict | None:
    token = (access_token or "").strip()
    if not token:
        return None
    try:
        r = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
    except Exception:
        logger.exception("google_oauth_userinfo_failed")
        return None
    if r.status_code != 200:
        logger.info("google_oauth_userinfo_status=%s", r.status_code)
        return None
    try:
        data = r.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None
