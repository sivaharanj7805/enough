"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Central configuration for the Enough backend."""

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""
    database_url: str = ""

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

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
