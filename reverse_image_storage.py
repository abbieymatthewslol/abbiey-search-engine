"""Short-lived Supabase Storage backed hosting for reverse-image uploads.

The Bing reverse-image endpoint needs a public HTTPS URL to fetch the user's
upload once. Historically that meant the app had to serve the bytes itself at
``/api/reverse-image/preview/<token>``, which required ``SITE_URL`` to be set
to a public HTTPS origin. Serverless previews and first-run self-hosts do not
have that guarantee, so uploads silently 422'd.

This module replaces that in-memory/echo-back approach with a signed, short
lived object in a private Supabase Storage bucket (``reverse-image-uploads``):

    put_object(raw, mime)  -> (signed_url, delete_handle)
    delete_object(handle)  -> None

The bucket is configured as *private* and the signed URL expires after
``SIGNED_URL_TTL_SECONDS`` (60s). A daily Supabase cron (see
``supabase/migrations/0001_reverse_image_uploads.sql``) sweeps any objects
older than 10 minutes, so even if ``delete_object`` is not reached (crash,
timeout) nothing lingers.

Fallbacks:
    * If Supabase env is missing, ``put_object`` returns ``None`` and the
      caller should fall back to the legacy in-memory preview cache.
    * All network errors are swallowed and reported as ``None`` so the
      feature degrades to the existing behaviour instead of 500'ing.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

BUCKET_NAME = "reverse-image-uploads"
SIGNED_URL_TTL_SECONDS = 60
UPLOAD_TIMEOUT_SECONDS = 12.0


@dataclass(frozen=True)
class StoredObject:
    """Handle required to delete an uploaded object after a reverse lookup."""

    bucket: str
    path: str


def _supabase_base() -> Optional[str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    return url or None


def _service_key() -> Optional[str]:
    return (
        (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        or (os.environ.get("SUPABASE_SECRET_KEY") or "").strip()
        or None
    )


def is_configured() -> bool:
    """True when we have enough env to attempt Supabase Storage uploads."""
    return bool(_supabase_base() and _service_key())


def _object_path(mime: str) -> str:
    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/avif": "avif",
    }.get(mime, "bin")
    return f"{int(time.time())}-{secrets.token_urlsafe(18)}.{ext}"


def put_object(raw: bytes, mime: str) -> Optional[Tuple[str, StoredObject]]:
    """Upload ``raw`` to the private bucket and return (signed_url, handle).

    Returns ``None`` if Supabase is not configured or the upload failed. The
    caller is expected to fall through to a local fallback in that case.
    """
    base = _supabase_base()
    key = _service_key()
    if not base or not key:
        return None

    path = _object_path(mime)
    object_url = f"{base}/storage/v1/object/{BUCKET_NAME}/{path}"
    sign_url = f"{base}/storage/v1/object/sign/{BUCKET_NAME}/{path}"
    auth = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
    }

    try:
        with httpx.Client(timeout=UPLOAD_TIMEOUT_SECONDS) as client:
            up = client.post(
                object_url,
                content=raw,
                headers={
                    **auth,
                    "Content-Type": mime or "application/octet-stream",
                    "x-upsert": "false",
                    "Cache-Control": "private, no-store, max-age=0",
                },
            )
            if up.status_code >= 300:
                logger.warning(
                    "reverse_image_storage_upload_failed status=%s body=%s",
                    up.status_code,
                    up.text[:200],
                )
                return None

            sign = client.post(
                sign_url,
                json={"expiresIn": SIGNED_URL_TTL_SECONDS},
                headers={**auth, "Content-Type": "application/json"},
            )
            if sign.status_code >= 300:
                logger.warning(
                    "reverse_image_storage_sign_failed status=%s body=%s",
                    sign.status_code,
                    sign.text[:200],
                )
                delete_object(StoredObject(bucket=BUCKET_NAME, path=path))
                return None

            body = sign.json() if sign.headers.get("content-type", "").startswith("application/json") else {}
            signed = body.get("signedURL") or body.get("signedUrl") or ""
            if not signed:
                delete_object(StoredObject(bucket=BUCKET_NAME, path=path))
                return None
            if signed.startswith("/"):
                signed = f"{base}/storage/v1{signed}"
            elif not signed.startswith("http"):
                signed = f"{base}/storage/v1/{signed.lstrip('/')}"
            return signed, StoredObject(bucket=BUCKET_NAME, path=path)
    except httpx.HTTPError:
        logger.warning("reverse_image_storage_network_error", exc_info=True)
        return None


def delete_object(handle: StoredObject) -> None:
    """Best-effort delete. Any failure is swallowed; the cron sweeper backs us up."""
    base = _supabase_base()
    key = _service_key()
    if not base or not key or not handle or not handle.path:
        return
    url = f"{base}/storage/v1/object/{handle.bucket}/{handle.path}"
    try:
        with httpx.Client(timeout=6.0) as client:
            client.delete(
                url,
                headers={"Authorization": f"Bearer {key}", "apikey": key},
            )
    except httpx.HTTPError:
        logger.info("reverse_image_storage_delete_failed (sweeper will reap)", exc_info=True)
