"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the Tended backend."""

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""  # From: Supabase dashboard → Settings → API → JWT secret
    database_url: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    frontend_url: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Anthropic (Claude API for consolidation drafts, oracle, cluster labels)
    anthropic_api_key: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_growth: str = ""
    stripe_price_scale: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    email_from: str = "Tended <reports@tended.app>"

    # Prospect Discovery (optional)
    google_cse_key: str = ""
    google_cse_id: str = ""

    # App
    secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:3000"

    # Database pool tuning
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10

    # Monitoring
    sentry_dsn: str = ""
    environment: str = "production"

    # Cron / internal endpoint auth
    cron_secret: str = ""
    admin_secret: str = ""  # For /admin/* endpoints

    # Slack notifications (webhook URL)
    slack_webhook_url: str = ""

    # Security
    allowed_hosts: str = ""  # comma-separated, empty = allow all
    rate_limit_auth: str = "10/minute"  # stricter limit for auth endpoints
    rate_limit_oracle: str = "10/minute"
    rate_limit_draft: str = "5/minute"
    session_max_age_seconds: int = 86400  # 24h

    @property
    def allowed_host_list(self) -> list[str]:
        if not self.allowed_hosts:
            return []
        return [h.strip() for h in self.allowed_hosts.split(",")]

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


def validate_production(settings: "Settings | None" = None) -> None:
    """Enforce required secrets in production. Call at application startup."""
    import logging
    _log = logging.getLogger(__name__)

    if settings is None:
        settings = get_settings()

    if settings.environment != "production":
        return

    errors: list[str] = []

    if settings.secret_key in ("", "change-me-in-production"):
        errors.append("SECRET_KEY must be set to a secure random value in production")

    if not settings.supabase_url:
        errors.append("SUPABASE_URL is required in production")

    if not settings.supabase_jwt_secret:
        errors.append("SUPABASE_JWT_SECRET is required in production")

    if not settings.cron_secret:
        errors.append(
            "CRON_SECRET is not set — cron endpoints are unprotected in production"
        )

    if not settings.stripe_secret_key:
        errors.append("STRIPE_SECRET_KEY is required in production")

    if not settings.stripe_webhook_secret:
        errors.append("STRIPE_WEBHOOK_SECRET is required in production")

    if not settings.stripe_price_growth:
        errors.append("STRIPE_PRICE_GROWTH is required — create a Stripe price and set the ID")

    if not settings.stripe_price_scale:
        errors.append("STRIPE_PRICE_SCALE is required — create a Stripe price and set the ID")

    if not settings.resend_api_key:
        errors.append("RESEND_API_KEY is required in production — weekly reports need email delivery")

    if not settings.sentry_dsn:
        _log.warning("SENTRY_DSN is not set — error monitoring is disabled in production")

    if not settings.openai_api_key:
        errors.append("OPENAI_API_KEY is required in production — embeddings will fail")

    if not settings.anthropic_api_key:
        errors.append("ANTHROPIC_API_KEY is required in production — Oracle and consolidation will fail")

    if not settings.frontend_url:
        errors.append("FRONTEND_URL is required in production")
    elif settings.frontend_url.startswith("http://localhost"):
        _log.warning("FRONTEND_URL points to localhost in production")

    if not settings.google_redirect_uri:
        _log.warning("GOOGLE_REDIRECT_URI is not set — Google OAuth will not work")
    elif settings.google_redirect_uri.startswith("http://localhost"):
        _log.warning("GOOGLE_REDIRECT_URI points to localhost in production")

    if "*" in settings.cors_origin_list:
        _log.warning(
            "CORS_ORIGINS contains '*' in production — this allows any origin to access the API"
        )

    if errors:
        raise RuntimeError(
            "Production configuration errors:\n" + "\n".join(f"  • {e}" for e in errors)
        )
