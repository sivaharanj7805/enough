"""Shared dependencies used across routers."""

import hmac
import logging
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import Depends, Header, HTTPException

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

    # Try Supabase JWT validation
    try:
        import jwt

        from app.config import get_settings

        settings = get_settings()
        jwt_secret = settings.supabase_jwt_secret or settings.secret_key

        if jwt_secret and jwt_secret != "change-me-in-production":
            decoded = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": True, "verify_aud": False},
            )
            user_id = decoded.get("sub")
            if user_id:
                return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please sign in again")
    except jwt.InvalidTokenError:
        # Not a valid JWT — fall through to UUID dev fallback
        pass
    except ImportError:
        pass

    # Dev-only fallback: treat token as raw user_id (UUID format check)
    # NEVER allow this in production — require proper JWT validation
    from app.config import get_settings
    _settings = get_settings()
    if _settings.environment != "production":
        try:
            UUID(token)  # Validate it's at least a valid UUID
            logger.warning("Using dev UUID fallback for auth — NOT safe for production")
            return token
        except ValueError:
            pass

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
        # No cron secret configured — reject in production, warn in dev
        if settings.environment == "production":
            raise HTTPException(
                status_code=503,
                detail="Cron endpoint is disabled — CRON_SECRET is not configured",
            )
        logger.warning("CRON_SECRET not set — cron endpoints are unprotected (dev mode)")
        return

    if not x_cron_secret:
        raise HTTPException(status_code=401, detail="Missing X-Cron-Secret header")

    if not hmac.compare_digest(x_cron_secret, settings.cron_secret):
        raise HTTPException(status_code=403, detail="Invalid cron secret")


class SubscriptionGuard:
    """Dependency that checks subscription tier limits before allowing access."""

    def __init__(self, feature: str):
        self.feature = feature

    async def __call__(
        self,
        user_id: Annotated[str, Depends(get_current_user_id)],
        db: Annotated[asyncpg.Connection, Depends(get_db)],
    ) -> None:
        from app.services.stripe_service import StripeService

        service = StripeService()
        allowed = await service.check_usage_limits(db, user_id, self.feature)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Your plan does not include access to {self.feature}, or you have reached your usage limit. Please upgrade.",
            )


# Pre-built guards for common features
require_oracle = SubscriptionGuard("oracle")
require_consolidation = SubscriptionGuard("consolidation")
require_site_limit = SubscriptionGuard("sites")


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
