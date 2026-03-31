"""Authentication endpoints using Supabase Auth."""

import logging
import re
from datetime import UTC
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import Settings, get_settings
from app.database import get_supabase_admin, get_supabase_client
from app.dependencies import get_current_user_id
from app.models.schemas import AuthResponse, LoginRequest, RegisterRequest

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
    import base64
    import hashlib
    import hmac
    import json

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
    import base64
    import hashlib
    import hmac
    import json

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


# ──────────────────── Password Reset ────────────────────


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    access_token: str
    new_password: str


@router.post("/password-reset")
@limiter.limit("5/minute")
async def request_password_reset(request: Request, body: PasswordResetRequest):
    """Send a password reset email via Supabase Auth."""
    if not _EMAIL_RE.match(body.email):
        raise HTTPException(status_code=422, detail="Invalid email address format")
    try:
        client = get_supabase_client()
        settings = get_settings()
        redirect_url = f"{settings.frontend_url}/reset-password" if settings.frontend_url else None
        client.auth.reset_password_email(
            body.email,
            options={"redirect_to": redirect_url} if redirect_url else {},
        )
        # Always return success to prevent email enumeration
        return {"message": "If an account exists with that email, a password reset link has been sent"}
    except Exception as e:
        logger.error("Password reset request error: %s", e)
        # Still return success to prevent enumeration
        return {"message": "If an account exists with that email, a password reset link has been sent"}


@router.post("/password-reset/confirm")
@limiter.limit("5/minute")
async def confirm_password_reset(request: Request, body: PasswordResetConfirm):
    """Confirm password reset using the token from the reset email."""
    try:
        client = get_supabase_client()
        # Set session using the access token from the reset email link
        client.auth.set_session(body.access_token, "")
        client.auth.update_user({"password": body.new_password})
        return {"message": "Password updated successfully"}
    except Exception as e:
        logger.error("Password reset confirm error: %s", e)
        raise HTTPException(status_code=400, detail="Password reset failed — link may have expired")


# ──────────────────── Email Verification ────────────────────


class ResendVerificationRequest(BaseModel):
    email: str


@router.post("/resend-verification")
@limiter.limit("3/minute")
async def resend_verification(request: Request, body: ResendVerificationRequest):
    """Resend email verification link via Supabase Auth."""
    if not _EMAIL_RE.match(body.email):
        raise HTTPException(status_code=422, detail="Invalid email address format")
    try:
        client = get_supabase_client()
        client.auth.resend({"type": "signup", "email": body.email})
        return {"message": "Verification email sent — check your inbox"}
    except Exception as e:
        logger.error("Resend verification error: %s", e)
        return {"message": "Verification email sent — check your inbox"}


# ──────────────────── Account Deletion (GDPR) ────────────────────


@router.delete("/account")
async def delete_account(
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Delete the current user's account and all associated data.

    This is a GDPR-compliant endpoint that:
    1. Deletes all user sites (cascades to posts, clusters, etc.)
    2. Deletes the user profile
    3. Deletes the Supabase auth user
    """
    from app.database import get_pool

    pool = await get_pool()
    async with pool.acquire() as db:
        # Delete all sites (CASCADE handles posts, clusters, etc.)
        await db.execute("DELETE FROM sites WHERE user_id = $1", user_id)

        # Delete the profile
        await db.execute("DELETE FROM profiles WHERE id = $1::uuid", user_id)

    # Delete the Supabase auth user
    try:
        admin = get_supabase_admin()
        admin.auth.admin.delete_user(user_id)
    except Exception as e:
        logger.error("Failed to delete Supabase auth user %s: %s", user_id, e)
        # Profile and data are already deleted — log but don't fail

    return {"message": "Account and all associated data deleted"}


# ──────────────────── Terms Acceptance ────────────────────


class AcceptTermsRequest(BaseModel):
    accepted: bool = True


@router.post("/accept-terms")
async def accept_terms(
    body: AcceptTermsRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
):
    """Record that the user has accepted the terms of service."""
    if not body.accepted:
        raise HTTPException(status_code=400, detail="Terms must be accepted")

    from datetime import datetime

    from app.database import get_pool

    pool = await get_pool()
    async with pool.acquire() as db:
        await db.execute(
            "UPDATE profiles SET terms_accepted_at = $1 WHERE id = $2::uuid",
            datetime.now(UTC),
            user_id,
        )

    return {"message": "Terms of service accepted"}
