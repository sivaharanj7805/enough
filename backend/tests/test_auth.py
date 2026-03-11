"""Tests for authentication dependency."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

import jwt
from fastapi import HTTPException

from tests.conftest import TEST_USER_ID


@pytest.mark.asyncio
class TestAuthDependency:
    """Tests for get_current_user_id."""

    async def test_valid_jwt_token(self):
        """Valid JWT with sub claim should return user_id."""
        from app.dependencies import get_current_user_id

        secret = "test-secret-key-for-tests"
        payload = {
            "sub": TEST_USER_ID,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")
        header = f"Bearer {token}"

        mock_settings = MagicMock()
        mock_settings.supabase_key = "some-key"
        mock_settings.supabase_url = "https://test.supabase.co"
        mock_settings.secret_key = secret

        with patch("app.config.get_settings", return_value=mock_settings):
            user_id = await get_current_user_id(header)
        assert user_id == TEST_USER_ID

    async def test_expired_jwt_raises(self):
        """Expired JWT should raise 401."""
        from app.dependencies import get_current_user_id

        secret = "test-secret-key-for-tests"
        payload = {
            "sub": TEST_USER_ID,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        mock_settings = MagicMock()
        mock_settings.supabase_key = "some-key"
        mock_settings.supabase_url = "https://test.supabase.co"
        mock_settings.secret_key = secret

        with patch("app.config.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_id(f"Bearer {token}")
            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()

    async def test_invalid_token_raises(self):
        """Completely invalid token should raise 401."""
        from app.dependencies import get_current_user_id

        mock_settings = MagicMock()
        mock_settings.supabase_key = "some-key"
        mock_settings.supabase_url = "https://test.supabase.co"
        mock_settings.secret_key = "test-secret"

        with patch("app.config.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_id("Bearer not-a-jwt-not-a-uuid")
            assert exc_info.value.status_code == 401

    async def test_missing_token_raises(self):
        """Empty authorization header should raise 401."""
        from app.dependencies import get_current_user_id

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id("Bearer ")
        assert exc_info.value.status_code == 401

    async def test_dev_mode_uuid_fallback(self):
        """In dev mode (no supabase config), valid UUID token should work."""
        from app.dependencies import get_current_user_id

        mock_settings = MagicMock()
        mock_settings.supabase_key = ""
        mock_settings.supabase_url = ""
        mock_settings.secret_key = "test"

        with patch("app.config.get_settings", return_value=mock_settings):
            user_id = await get_current_user_id(f"Bearer {TEST_USER_ID}")
        assert user_id == TEST_USER_ID

    async def test_jwt_without_sub_raises(self):
        """JWT without sub claim should raise 401."""
        from app.dependencies import get_current_user_id

        secret = "test-secret-key-for-tests"
        payload = {
            "email": "test@test.com",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, secret, algorithm="HS256")

        mock_settings = MagicMock()
        mock_settings.supabase_key = "some-key"
        mock_settings.supabase_url = "https://test.supabase.co"
        mock_settings.secret_key = secret

        with patch("app.config.get_settings", return_value=mock_settings):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_id(f"Bearer {token}")
            assert exc_info.value.status_code == 401
