"""Authentication endpoints using Supabase Auth."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
import httpx

from app.config import get_settings, Settings
from app.database import get_supabase_client
from app.models.schemas import RegisterRequest, LoginRequest, AuthResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _settings() -> Settings:
    return get_settings()


@router.post("/register", response_model=AuthResponse)
async def register(body: RegisterRequest, settings: Annotated[Settings, Depends(_settings)]):
    """Register a new user via Supabase Auth."""
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
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
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


@router.get("/google")
async def google_oauth_redirect(settings: Annotated[Settings, Depends(_settings)]):
    """Redirect to Google OAuth consent screen for GA4/GSC access."""
    scopes = [
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/webmasters.readonly",
    ]
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth"
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=f"{url}?{query}")


@router.get("/google/callback")
async def google_oauth_callback(
    code: Annotated[str, Query()],
    settings: Annotated[Settings, Depends(_settings)],
):
    """Exchange Google OAuth code for tokens."""
    try:
        async with httpx.AsyncClient() as client:
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

        # Return tokens — the frontend should call PUT /sites/{id} to store
        # the refresh_token with the appropriate site
        return {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens.get("expires_in"),
            "message": "Use PUT /sites/{site_id}/google-token to store the refresh_token.",
        }
    except httpx.HTTPStatusError as e:
        logger.error("Google OAuth token exchange failed: %s", e.response.text)
        raise HTTPException(status_code=400, detail="OAuth token exchange failed")
    except Exception as e:
        logger.error("Google OAuth callback error: %s", e)
        raise HTTPException(status_code=500, detail="Internal error during OAuth")
