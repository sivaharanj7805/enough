"""Authentication endpoints using Supabase Auth."""

import logging
import os
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
import httpx
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings, Settings
from app.database import get_supabase_client
from app.models.schemas import RegisterRequest, LoginRequest, AuthResponse

logger = logging.getLogger(__name__)
router = APIRouter()

limiter = Limiter(key_func=get_remote_address)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _settings() -> Settings:
    return get_settings()


@router.post("/register", response_model=AuthResponse)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, settings: Annotated[Settings, Depends(_settings)]):
    """Register a new user via Supabase Auth."""
    if not _EMAIL_RE.match(body.email):
        raise HTTPException(status_code=422, detail="Invalid email address format")
    try:
        client = get_supabase_client()
        result = client.auth.sign_up({
            "email": body.email,
            "password": body.password,
            "options": {"data": {"full_name": body.full_name or ""}},
        })

        if not result.user:
            raise HTTPException(status_code=400, detail="Registration failed")

        session = result.session
        if not session:
            # Email confirmation may be required
            return AuthResponse(
                access_token="",
                refresh_token="",
                user_id=str(result.user.id),
                email=body.email,
            )

        return AuthResponse(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user_id=str(result.user.id),
            email=body.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Registration error: %s", e)
        raise HTTPException(status_code=400, detail="Registration failed — check your email and password")


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """Sign in with email/password."""
    try:
        client = get_supabase_client()
        result = client.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })

        if not result.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return AuthResponse(
            access_token=result.session.access_token,
            refresh_token=result.session.refresh_token,
            user_id=str(result.user.id),
            email=body.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login error: %s", e)
        raise HTTPException(status_code=401, detail="Invalid credentials")


@router.post("/magic-link")
@limiter.limit("5/minute")
async def send_magic_link(request: Request, body: LoginRequest):
    """Send a magic link (passwordless) email via Supabase Auth."""
    try:
        client = get_supabase_client()
        client.auth.sign_in_with_otp({
            "email": body.email,
            "options": {"should_create_user": True},
        })
        return {"message": "Magic link sent — check your email"}
    except Exception as e:
        logger.error("Magic link error: %s", e)
        raise HTTPException(status_code=400, detail="Failed to send magic link")


@router.get("/google")
async def google_oauth_redirect(
    settings: Annotated[Settings, Depends(_settings)],
    site_id: str = Query(default="", description="Site ID to link Google account to"),
):
    """Redirect to Google OAuth consent screen for GA4/GSC access.

    Pass ?site_id=<uuid> to automatically link the token to a site after auth.
    The site_id is encoded in the OAuth state parameter (HMAC-signed to prevent tampering).
    """
    import hashlib
    import hmac
    import json
    import base64

    scopes = [
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/webmasters.readonly",
    ]

    # Build signed state to carry site_id through the OAuth flow
    state_data = {"site_id": site_id} if site_id else {}
    state_json = json.dumps(state_data, separators=(",", ":"))
    state_b64 = base64.urlsafe_b64encode(state_json.encode()).decode()
    state_sig = hmac.new(
        settings.secret_key.encode(),
        state_b64.encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    state = f"{state_b64}.{state_sig}"

    from urllib.parse import urlencode
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth"
    return RedirectResponse(url=f"{url}?{urlencode(params)}")


@router.get("/google/callback")
async def google_oauth_callback(
    code: Annotated[str, Query()],
    settings: Annotated[Settings, Depends(_settings)],
    state: str = Query(default=""),
):
    """Exchange Google OAuth code for tokens.

    If state contains a valid signed site_id, automatically stores the refresh
    token for that site (requires the user to be authenticated).
    """
    import hashlib
    import hmac
    import json
    import base64

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            tokens = resp.json()

        # Verify and extract state
        site_id = None
        if state and "." in state:
            state_b64, state_sig = state.rsplit(".", 1)
            expected_sig = hmac.new(
                settings.secret_key.encode(),
                state_b64.encode(),
                hashlib.sha256,
            ).hexdigest()[:16]

            if hmac.compare_digest(state_sig, expected_sig):
                try:
                    state_data = json.loads(base64.urlsafe_b64decode(state_b64))
                    site_id = state_data.get("site_id")
                except (json.JSONDecodeError, Exception):
                    pass
            else:
                logger.warning(
                    "OAuth state signature mismatch — rejecting callback (possible tampering)"
                )
                raise HTTPException(
                    status_code=400,
                    detail="Invalid OAuth state — please restart the authorization flow",
                )

        # Auto-store tokens if we have a valid site_id
        if site_id and tokens.get("refresh_token"):
            import time
            from app.database import get_pool
            from app.services.google_auth import encrypt_token
            try:
                from uuid import UUID
                site_uuid = UUID(site_id)
                token_data = dict(tokens)
                token_data["expires_at"] = time.time() + tokens.get("expires_in", 3600)
                encrypted = encrypt_token(token_data)
                pool = await get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE sites SET google_tokens = $1 WHERE id = $2",
                        encrypted, site_uuid,
                    )
                logger.info("Auto-stored Google tokens for site %s", site_id)
            except Exception as store_err:
                logger.error("Failed to auto-store tokens: %s", store_err)

        # Redirect to frontend settings with status
        frontend_url = settings.frontend_url
        if site_id and tokens.get("refresh_token"):
            return RedirectResponse(f"{frontend_url}/settings?google_connected=1&site_id={site_id}")
        else:
            # Fallback: return tokens as JSON so user can manually store
            return {
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in"),
                "site_id": site_id,
                "message": (
                    f"Token ready for site {site_id}. Call PUT /sites/{site_id}/google-token."
                    if site_id
                    else "Use PUT /sites/{site_id}/google-token to store the refresh_token."
                ),
            }
    except httpx.HTTPStatusError as e:
        logger.error("Google OAuth token exchange failed: %s", e.response.text)
        raise HTTPException(status_code=400, detail="OAuth token exchange failed")
    except Exception as e:
        logger.error("Google OAuth callback error: %s", e)
        raise HTTPException(status_code=500, detail="Internal error during OAuth")
