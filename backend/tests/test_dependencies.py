"""Tests for shared dependencies — cron secret, subscription guard, site ownership."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import HTTPException

from tests.conftest import TEST_USER_ID, TEST_SITE_ID, MockConnection, make_record


@pytest.mark.asyncio
class TestCronSecretVerification:
    """Tests for verify_cron_secret dependency."""

    async def test_valid_cron_secret(self):
        """Correct secret should pass."""
        from app.dependencies import verify_cron_secret

        mock_settings = MagicMock()
        mock_settings.cron_secret = "my-secret"
        mock_settings.environment = "production"

        with patch("app.config.get_settings", return_value=mock_settings):
            # Should not raise
            await verify_cron_secret(x_cron_secret="my-secret")

    async def test_wrong_cron_secret(self):
        """Wrong secret should raise 403."""
        from app.dependencies import verify_cron_secret

        mock_settings = MagicMock()
        mock_settings.cron_secret = "my-secret"
        mock_settings.environment = "production"

        with patch("app.config.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await verify_cron_secret(x_cron_secret="wrong-secret")
            assert exc_info.value.status_code == 403

    async def test_missing_cron_header(self):
        """Missing header with configured secret should raise 401."""
        from app.dependencies import verify_cron_secret

        mock_settings = MagicMock()
        mock_settings.cron_secret = "my-secret"
        mock_settings.environment = "production"

        with patch("app.config.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await verify_cron_secret(x_cron_secret=None)
            assert exc_info.value.status_code == 401

    async def test_no_secret_configured_production(self):
        """No secret in production should raise 503."""
        from app.dependencies import verify_cron_secret

        mock_settings = MagicMock()
        mock_settings.cron_secret = ""
        mock_settings.environment = "production"

        with patch("app.config.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await verify_cron_secret(x_cron_secret=None)
            assert exc_info.value.status_code == 503

    async def test_no_secret_configured_dev(self):
        """No secret in dev mode should pass with warning."""
        from app.dependencies import verify_cron_secret

        mock_settings = MagicMock()
        mock_settings.cron_secret = ""
        mock_settings.environment = "development"

        with patch("app.config.get_settings", return_value=mock_settings):
            # Should not raise
            await verify_cron_secret(x_cron_secret=None)


@pytest.mark.asyncio
class TestSubscriptionGuard:
    """Tests for SubscriptionGuard dependency."""

    async def test_allowed_feature(self):
        """Guard should pass when usage is within limits."""
        from app.dependencies import SubscriptionGuard

        guard = SubscriptionGuard("oracle")
        mock_service = MagicMock()
        mock_service.check_usage_limits = AsyncMock(return_value=True)

        db = MockConnection()

        with patch("app.services.stripe_service.StripeService", return_value=mock_service):
            await guard(user_id=TEST_USER_ID, db=db)

    async def test_blocked_feature(self):
        """Guard should raise 403 when limit exceeded."""
        from app.dependencies import SubscriptionGuard

        guard = SubscriptionGuard("oracle")
        mock_service = MagicMock()
        mock_service.check_usage_limits = AsyncMock(return_value=False)

        db = MockConnection()

        with patch("app.services.stripe_service.StripeService", return_value=mock_service):
            with pytest.raises(HTTPException) as exc_info:
                await guard(user_id=TEST_USER_ID, db=db)
            assert exc_info.value.status_code == 403
            assert "oracle" in exc_info.value.detail


@pytest.mark.asyncio
class TestGetVerifiedSite:
    """Tests for get_verified_site dependency."""

    async def test_site_found(self):
        """Should return site dict when user owns it."""
        from app.dependencies import get_verified_site

        db = MockConnection()
        db._fetchrow_returns = [
            make_record(id=TEST_SITE_ID, user_id=TEST_USER_ID, name="Test Site")
        ]

        result = await get_verified_site(TEST_SITE_ID, TEST_USER_ID, db)
        assert result["id"] == TEST_SITE_ID
        assert result["name"] == "Test Site"

    async def test_site_not_found(self):
        """Should raise 404 when site doesn't exist or user doesn't own it."""
        from app.dependencies import get_verified_site

        db = MockConnection()
        db._fetchrow_returns = [None]

        with pytest.raises(HTTPException) as exc_info:
            await get_verified_site(TEST_SITE_ID, TEST_USER_ID, db)
        assert exc_info.value.status_code == 404
