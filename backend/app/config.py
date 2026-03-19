"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration for the Enough backend."""

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""  # From: Supabase dashboard → Settings → API → JWT secret
    database_url: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    frontend_url: str = "http://localhost:3000"

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
    email_from: str = "Enough <reports@enough.app>"

    # App
    secret_key: str = "change-me-in-production"
    cors_origins: str = "http://localhost:3000"

    # Monitoring
    sentry_dsn: str = ""
    environment: str = "production"

    # Cron / internal endpoint auth
    cron_secret: str = ""

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

    if "*" in settings.cors_origin_list:
        _log.warning(
            "CORS_ORIGINS contains '*' in production — this allows any origin to access the API"
        )

    if errors:
        raise RuntimeError(
            "Production configuration errors:\n" + "\n".join(f"  • {e}" for e in errors)
        )
