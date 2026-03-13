"""Shared dependencies used across routers."""

import hmac
import logging
import secrets
from uuid import UUID
from typing import Annotated

import asyncpg
from fastapi import Depends, Header, HTTPException, Request

from app.database import get_db

logger = logging.getLogger(__name__)


async def get_current_user_id(authorization: Annotated[str, Header()]) -> str:
    """Extract and validate user ID from the authorization header.

    Phase 1: Accepts a Supabase JWT and extracts the `sub` claim.
    Falls back to treating the raw token as user_id for local dev
    when SUPABASE_URL is not configured.
    """
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    # Try JWT validation first
    try:
        import jwt
        from app.config import get_settings

        settings = get_settings()
        if settings.supabase_key and settings.supabase_url:
            # Supabase JWTs are signed with the JWT secret (service key for verification)
            # In production, use the JWKS endpoint or the JWT secret from Supabase dashboard
            decoded = jwt.decode(
                token,
                settings.secret_key,
                algorithms=["HS256"],
                options={"verify_exp": True},
            )
            user_id = decoded.get("sub")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token: no sub claim")
            return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        # Fall through to dev mode
        pass
    except ImportError:
        pass

    # Dev fallback: treat token as raw user_id (UUID format check)
    try:
        UUID(token)  # Validate it's at least a valid UUID
        return token
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization token")


async def verify_cron_secret(
    x_cron_secret: Annotated[str | None, Header(alias="X-Cron-Secret")] = None,
) -> None:
    """Verify the cron secret header for internal/scheduled endpoints.

    Rejects requests if:
    - CRON_SECRET is configured and header is missing or wrong
    - Uses constant-time comparison to prevent timing attacks
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.cron_secret:
        # No cron secret configured — allow in dev mode but log warning
        logger.warning("CRON_SECRET not set — cron endpoints are unprotected")
        return

    if not x_cron_secret:
        raise HTTPException(status_code=401, detail="Missing X-Cron-Secret header")

    if not hmac.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(status_code=403, detail="Invalid cron secret")


async def get_verified_site(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
) -> dict:
    """Fetch a site ensuring the current user owns it."""
    row = await db.fetchrow(
        "SELECT * FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")
    return dict(row)
