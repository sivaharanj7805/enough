"""Tests for site CRUD logic and ownership verification."""

import pytest
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

from tests.conftest import TEST_USER_ID, TEST_SITE_ID, make_record


class TestSiteOwnership:
    """Test site ownership verification."""

    @pytest.mark.asyncio
    async def test_verify_site_owned(self):
        """User who owns the site should pass verification."""
        from app.dependencies import get_verified_site

        mock_db = AsyncMock()
        mock_db.fetchrow = AsyncMock(return_value=make_record(
            id=TEST_SITE_ID, user_id=TEST_USER_ID, name="Test Site",
            domain="test.com", cms_type="wordpress",
        ))

        result = await get_verified_site(TEST_SITE_ID, TEST_USER_ID, mock_db)
        assert result["id"] == TEST_SITE_ID

    @pytest.mark.asyncio
    async def test_verify_site_not_owned(self):
        """User who doesn't own site should get 404."""
        from app.dependencies import get_verified_site

        mock_db = AsyncMock()
        mock_db.fetchrow = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_verified_site(TEST_SITE_ID, "other-user-id", mock_db)
        assert exc_info.value.status_code == 404


class TestSiteResponseSanitization:
    """Test that sensitive fields are stripped from responses."""

    def test_sanitize_strips_password(self):
        from app.routers.sites import _sanitize_site_response
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        row = make_record(
            id=TEST_SITE_ID,
            user_id=TEST_USER_ID,
            name="Test Site",
            domain="test.com",
            cms_type="wordpress",
            wordpress_url="https://test.com/wp-json",
            wordpress_app_password="encrypted-password",
            google_refresh_token="encrypted-token",
            sitemap_url=None,
            ga4_property_id=None,
            gsc_site_url=None,
            last_crawl_at=None,
            last_analytics_sync_at=None,
            created_at=now,
            updated_at=now,
        )
        result = _sanitize_site_response(row)
        # Should not contain the encrypted password
        result_dict = result.model_dump() if hasattr(result, 'model_dump') else result.dict()
        assert "wordpress_app_password" not in result_dict
        assert "google_refresh_token" not in result_dict

    def test_sanitize_preserves_public_fields(self):
        from app.routers.sites import _sanitize_site_response
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        row = make_record(
            id=TEST_SITE_ID,
            user_id=TEST_USER_ID,
            name="My Blog",
            domain="myblog.com",
            cms_type="wordpress",
            wordpress_url="https://myblog.com/wp-json",
            wordpress_app_password=None,
            google_refresh_token=None,
            sitemap_url="https://myblog.com/sitemap.xml",
            ga4_property_id="properties/12345",
            gsc_site_url="https://myblog.com",
            last_crawl_at=None,
            last_analytics_sync_at=None,
            created_at=now,
            updated_at=now,
        )
        result = _sanitize_site_response(row)
        assert result.name == "My Blog"
        assert result.domain == "myblog.com"
