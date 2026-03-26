"""Google OAuth2 service for GSC and GA4 integration."""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
    "openid",
    "email",
]


def _get_fernet() -> Fernet:
    key = os.environ.get("FERNET_KEY", "")
    if not key:
        # Generate a stable key from secret_key via Settings (single source of truth)
        import base64
        import hashlib

        from app.config import get_settings
        settings = get_settings()
        secret = settings.secret_key
        digest = hashlib.sha256(secret.encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(token_data: dict) -> str:
    """Encrypt token dict for storage."""
    f = _get_fernet()
    return f.encrypt(json.dumps(token_data).encode()).decode()


def decrypt_token(encrypted: str) -> dict:
    """Decrypt stored token."""
    f = _get_fernet()
    return json.loads(f.decrypt(encrypted.encode()).decode())


def get_auth_url(state: str) -> str:
    """Generate Google OAuth2 authorization URL."""
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": os.environ["GOOGLE_REDIRECT_URI"],
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Exchange authorization code for tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": os.environ["GOOGLE_REDIRECT_URI"],
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """Refresh an expired access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        data = resp.json()
        # refresh_token is not returned on refresh — keep the original
        if "refresh_token" not in data:
            data["refresh_token"] = refresh_token
        return data


async def get_valid_token(db, site_id, user_id: str | None = None) -> str | None:
    """Get a valid access token for a site, refreshing if needed."""
    import time
    if user_id:
        row = await db.fetchrow(
            "SELECT google_tokens FROM sites WHERE id = $1 AND user_id = $2",
            site_id, user_id,
        )
    else:
        row = await db.fetchrow(
            "SELECT google_tokens FROM sites WHERE id = $1",
            site_id,
        )
    if not row or not row["google_tokens"]:
        return None

    try:
        token_data = decrypt_token(row["google_tokens"])
    except Exception:
        logger.warning("Failed to decrypt google_tokens for site %s", site_id)
        return None

    # Guard against corrupted token data (e.g. error responses stored accidentally)
    if "error" in token_data or ("access_token" not in token_data and "refresh_token" not in token_data):
        logger.warning("Corrupted token data for site %s — clearing", site_id)
        await db.execute("UPDATE sites SET google_tokens = NULL WHERE id = $1", site_id)
        return None

    expires_at = token_data.get("expires_at", 0)
    if time.time() < expires_at - 60 and token_data.get("access_token"):
        return token_data["access_token"]

    # Refresh
    try:
        new_tokens = await refresh_access_token(token_data["refresh_token"])
        new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 3600)
        encrypted = encrypt_token(new_tokens)
        await db.execute(
            "UPDATE sites SET google_tokens = $1 WHERE id = $2",
            encrypted, site_id,
        )
        return new_tokens["access_token"]
    except Exception as e:
        logger.error("Failed to refresh Google token for site %s: %s", site_id, e)
        return None
