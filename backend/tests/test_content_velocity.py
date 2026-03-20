"""Tests for content velocity tracking service."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import UUID

from tests.conftest import MockConnection, TEST_SITE_ID


@pytest.mark.asyncio
class TestContentVelocityTracker:
    """Test publishing velocity computation and trend detection."""

    async def test_growing_velocity(self):
        """30d velocity >> 90d velocity should be 'growing'."""
        from app.services.content_velocity import ContentVelocityTracker

        db = MockConnection()
        # count_30d=20, count_90d=25, total=50
        db._fetchval_returns = [20, 25, 50]
        db._execute_results = ["UPDATE 1"]

        tracker = ContentVelocityTracker()
        result = await tracker.compute_for_site(db, TEST_SITE_ID)

        assert result["trend"] == "growing"
        assert result["count_30d"] == 20
        assert result["count_90d"] == 25
        assert result["velocity_30d"] > 0

    async def test_declining_velocity(self):
        """30d velocity << 90d velocity should be 'declining'."""
        from app.services.content_velocity import ContentVelocityTracker

        db = MockConnection()
        # count_30d=1, count_90d=30, total=100
        db._fetchval_returns = [1, 30, 100]
        db._execute_results = ["UPDATE 1"]

        tracker = ContentVelocityTracker()
        result = await tracker.compute_for_site(db, TEST_SITE_ID)

        assert result["trend"] == "declining"

    async def test_stable_velocity(self):
        """Similar 30d and 90d velocity should be 'stable'."""
        from app.services.content_velocity import ContentVelocityTracker

        db = MockConnection()
        # count_30d=4, count_90d=12, total=50 → same posts/week ratio
        db._fetchval_returns = [4, 12, 50]
        db._execute_results = ["UPDATE 1"]

        tracker = ContentVelocityTracker()
        result = await tracker.compute_for_site(db, TEST_SITE_ID)

        assert result["trend"] == "stable"

    async def test_zero_posts(self):
        """No posts should return stable with zero velocity."""
        from app.services.content_velocity import ContentVelocityTracker

        db = MockConnection()
        db._fetchval_returns = [0, 0, 0]
        db._execute_results = ["UPDATE 1"]

        tracker = ContentVelocityTracker()
        result = await tracker.compute_for_site(db, TEST_SITE_ID)

        assert result["trend"] == "stable"
        assert result["velocity_30d"] == 0
        assert result["velocity_90d"] == 0

    async def test_new_site_growing(self):
        """Posts only in last 30d with zero 90d baseline should be 'growing'."""
        from app.services.content_velocity import ContentVelocityTracker

        db = MockConnection()
        # count_30d=5, count_90d=5 (all recent), total=5
        db._fetchval_returns = [5, 5, 5]
        db._execute_results = ["UPDATE 1"]

        tracker = ContentVelocityTracker()
        result = await tracker.compute_for_site(db, TEST_SITE_ID)

        # 30d velocity is 5/4.28 = 1.17, 90d velocity is 5/12.86 = 0.39
        # 1.17 > 0.39 * 1.5 → growing
        assert result["trend"] == "growing"

    async def test_result_shape(self):
        """Result should contain all expected keys."""
        from app.services.content_velocity import ContentVelocityTracker

        db = MockConnection()
        db._fetchval_returns = [10, 30, 80]
        db._execute_results = ["UPDATE 1"]

        tracker = ContentVelocityTracker()
        result = await tracker.compute_for_site(db, TEST_SITE_ID)

        assert "velocity_30d" in result
        assert "velocity_90d" in result
        assert "trend" in result
        assert "count_30d" in result
        assert "count_90d" in result
        assert "total_posts" in result
