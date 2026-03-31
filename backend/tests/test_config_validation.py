"""Tests for production config validation and security settings."""
import pytest
from unittest.mock import patch


def test_validate_production_raises_on_default_secret_key():
    """Production startup should fail if secret key is the default value."""
    from app.config import Settings, validate_production

    settings = Settings(
        environment="production",
        secret_key="change-me-in-production",
        supabase_url="https://example.supabase.co",
        supabase_jwt_secret="valid-jwt-secret",
        cron_secret="valid-cron-secret",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production(settings)


def test_validate_production_raises_on_empty_secret_key():
    """Production startup should fail if secret key is empty."""
    from app.config import Settings, validate_production

    settings = Settings(
        environment="production",
        secret_key="",
        supabase_url="https://example.supabase.co",
        supabase_jwt_secret="valid-jwt-secret",
        cron_secret="valid-cron-secret",
    )
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production(settings)


def test_validate_production_passes_with_valid_config():
    """Production validation should pass with proper settings."""
    from app.config import Settings, validate_production

    settings = Settings(
        environment="production",
        secret_key="a-secure-random-key-64-chars-long-for-production-use-only-abc123",
        supabase_url="https://example.supabase.co",
        supabase_jwt_secret="valid-jwt-secret",
        cron_secret="valid-cron-secret",
        stripe_secret_key="sk_test_abc123",
        stripe_webhook_secret="whsec_abc123",
        stripe_price_growth="price_abc123",
        stripe_price_scale="price_xyz123",
        resend_api_key="re_abc123",
        openai_api_key="sk-abc123",
        anthropic_api_key="sk-ant-abc123",
        frontend_url="https://tended.app",
    )
    # Should not raise
    validate_production(settings)


def test_validate_production_skips_non_production():
    """Validation should be a no-op in development mode."""
    from app.config import Settings, validate_production

    settings = Settings(
        environment="development",
        secret_key="",  # Would fail in production
    )
    # Should not raise in development
    validate_production(settings)


def test_validate_production_warns_on_cors_wildcard(caplog):
    """Production with CORS wildcard should log a warning."""
    import logging
    from app.config import Settings, validate_production

    settings = Settings(
        environment="production",
        secret_key="a-secure-random-key-64-chars-long",
        supabase_url="https://example.supabase.co",
        supabase_jwt_secret="valid-jwt-secret",
        cron_secret="valid-cron-secret",
        stripe_secret_key="sk_test_abc123",
        stripe_webhook_secret="whsec_abc123",
        stripe_price_growth="price_abc123",
        stripe_price_scale="price_xyz123",
        resend_api_key="re_abc123",
        openai_api_key="sk-abc123",
        anthropic_api_key="sk-ant-abc123",
        frontend_url="https://tended.app",
        cors_origins="*",
    )
    with caplog.at_level(logging.WARNING):
        validate_production(settings)
    assert "CORS_ORIGINS contains '*'" in caplog.text


def test_validate_production_raises_missing_supabase_url():
    """Production startup should fail if Supabase URL is not set."""
    from app.config import Settings, validate_production

    settings = Settings(
        environment="production",
        secret_key="a-secure-random-key-64-chars-long",
        supabase_url="",  # Missing
        supabase_jwt_secret="valid-jwt-secret",
        cron_secret="valid-cron-secret",
    )
    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        validate_production(settings)
