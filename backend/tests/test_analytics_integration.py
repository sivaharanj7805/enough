"""Integration tests for analytics endpoints (/v1/sites/{id}/posts, /analytics)."""

import pytest
from datetime import datetime, timezone, date
from uuid import UUID
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from tests.conftest import (
    TEST_USER_ID, TEST_SITE_ID, TEST_POST_ID_A, TEST_POST_ID_B,
    MockConnection, make_record,
)

AUTH_HEADER = {"Authorization": f"Bearer {TEST_USER_ID}"}
NOW = datetime.now(timezone.utc)


def _site_exists():
    return make_record(id=TEST_SITE_ID)


def _post_row(post_id=TEST_POST_ID_A):
    return make_record(
        id=post_id,
        site_id=TEST_SITE_ID,
        url="/test-post",
        slug="test-post",
        title="Test Post Title",
        body_text="Some body text here.",
        publish_date=NOW,
        modified_date=NOW,
        cms_categories=["tech"],
        cms_tags=["python"],
        word_count=1500,
        content_hash="abc123",
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture
def mock_conn():
    return MockConnection()


def _make_pool_mock(conn):
    pool_obj = MagicMock()
    acm = MagicMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=None)
    pool_obj.acquire.return_value = acm
    return pool_obj


@pytest.fixture
def app_with_mocks(mock_conn):
    from app.config import get_settings
    get_settings.cache_clear()

    pool_obj = _make_pool_mock(mock_conn)

    with patch("app.database.get_pool") as mock_pool:
        async def _mock_get_pool():
            return pool_obj
        mock_pool.side_effect = _mock_get_pool

        from importlib import reload
        import app.main
        reload(app.main)
        the_app = app.main.app

        from app.database import get_db
        async def _override_get_db():
            yield mock_conn
        the_app.dependency_overrides[get_db] = _override_get_db

        yield the_app, mock_conn

        the_app.dependency_overrides.clear()


# ── List Posts ──


@pytest.mark.asyncio
async def test_list_posts_success(app_with_mocks):
    app, conn = app_with_mocks
    # _verify_site_ownership fetchrow
    conn._fetchrow_returns = [_site_exists()]
    # total count
    conn._fetchval_returns = [2]
    # post rows
    conn._fetch_returns = [[_post_row(TEST_POST_ID_A), _post_row(TEST_POST_ID_B)]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/sites/{TEST_SITE_ID}/posts", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["posts"]) == 2


@pytest.mark.asyncio
async def test_list_posts_with_pagination(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]
    conn._fetchval_returns = [50]
    conn._fetch_returns = [[_post_row()]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/posts?limit=10&offset=20",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 50


@pytest.mark.asyncio
async def test_list_posts_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/sites/{TEST_SITE_ID}/posts", headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_posts_no_auth(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/sites/{TEST_SITE_ID}/posts")

    assert resp.status_code == 422


# ── Get Post Detail ──


@pytest.mark.asyncio
async def test_get_post_detail_success(app_with_mocks):
    app, conn = app_with_mocks
    # _verify_site_ownership
    conn._fetchrow_returns = [
        _site_exists(),
        _post_row(),  # post row
    ]
    # ga4_metrics, gsc_metrics, internal_links
    conn._fetch_returns = [[], [], []]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/posts/{TEST_POST_ID_A}",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Post Title"
    assert "ga4_metrics" in data
    assert "gsc_metrics" in data
    assert "internal_links" in data


@pytest.mark.asyncio
async def test_get_post_detail_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists(), None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/posts/{TEST_POST_ID_A}",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── Analytics Overview ──


@pytest.mark.asyncio
async def test_analytics_overview_success(app_with_mocks):
    app, conn = app_with_mocks
    # _verify_site_ownership
    conn._fetchrow_returns = [
        _site_exists(),
        # ga4 aggregate
        make_record(
            total_pageviews=10000,
            total_sessions=5000,
            date_start=date(2025, 1, 1),
            date_end=date(2025, 3, 1),
        ),
        # gsc aggregate
        make_record(
            total_clicks=3000,
            total_impressions=50000,
            avg_position=12.5,
        ),
    ]
    conn._fetchval_returns = [100]  # total_posts

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/analytics/overview",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_posts"] == 100
    assert data["total_pageviews"] == 10000
    assert data["total_clicks"] == 3000
    assert data["avg_position"] == 12.5


@pytest.mark.asyncio
async def test_analytics_overview_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/analytics/overview",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analytics_overview_no_data(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [
        _site_exists(),
        make_record(total_pageviews=0, total_sessions=0, date_start=None, date_end=None),
        make_record(total_clicks=0, total_impressions=0, avg_position=None),
    ]
    conn._fetchval_returns = [0]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/analytics/overview",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_posts"] == 0
    assert data["total_pageviews"] == 0
