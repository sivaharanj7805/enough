"""Integration tests for ingestion endpoints (crawl, pipeline, cron)."""

import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from tests.conftest import (
    TEST_USER_ID, TEST_SITE_ID,
    MockConnection, make_record,
)

AUTH_HEADER = {"Authorization": f"Bearer {TEST_USER_ID}"}
NOW = datetime.now(timezone.utc)


def _site_row():
    return make_record(
        id=TEST_SITE_ID,
        user_id=UUID(TEST_USER_ID),
        name="My Blog",
        domain="example.com",
        cms_type="sitemap",
        wordpress_url=None,
        wordpress_app_password=None,
        sitemap_url="https://example.com/sitemap.xml",
        ga4_property_id=None,
        gsc_site_url=None,
        google_tokens=None,
        last_crawl_at=None,
        last_analytics_sync_at=None,
        created_at=NOW,
        updated_at=NOW,
        url_patterns=None,
    )


def _site_exists():
    return make_record(id=TEST_SITE_ID)


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


# ── Trigger Crawl ──


@pytest.mark.asyncio
async def test_trigger_crawl_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_row()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/crawl",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "Crawl started" in resp.json()["message"]


@pytest.mark.asyncio
async def test_trigger_crawl_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/crawl",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_trigger_crawl_no_auth(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(f"/v1/sites/{TEST_SITE_ID}/crawl")

    assert resp.status_code == 422


# ── Crawl Status ──


@pytest.mark.asyncio
async def test_crawl_status_idle(app_with_mocks):
    app, conn = app_with_mocks
    # _verify_ownership
    conn._fetchrow_returns = [_site_exists(), None]  # site exists, no crawl job

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/crawl/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


@pytest.mark.asyncio
async def test_crawl_status_in_progress(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [
        _site_exists(),
        make_record(
            site_id=TEST_SITE_ID,
            status="crawling",
            posts_found=50,
            posts_processed=25,
            started_at=NOW,
            completed_at=None,
            error=None,
        ),
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/crawl/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "crawling"
    assert data["posts_found"] == 50
    assert data["posts_processed"] == 25


@pytest.mark.asyncio
async def test_crawl_status_completed(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [
        _site_exists(),
        make_record(
            site_id=TEST_SITE_ID,
            status="completed",
            posts_found=100,
            posts_processed=100,
            started_at=NOW,
            completed_at=NOW,
            error=None,
        ),
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/crawl/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["posts_processed"] == 100


# ── Sync Analytics ──


@pytest.mark.asyncio
async def test_trigger_analytics_sync(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_row()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/sync-analytics",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "Analytics sync started" in resp.json()["message"]


# ── Generate Embeddings ──


@pytest.mark.asyncio
async def test_trigger_embeddings(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/generate-embeddings",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "Embedding generation started" in resp.json()["message"]


# ── Full Pipeline ──


@pytest.mark.asyncio
async def test_trigger_full_pipeline(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_row()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/pipeline",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "pipeline started" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_trigger_full_pipeline_with_url_patterns(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_row()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/pipeline",
            json={"url_patterns": ["/blog/", "/resources/"]},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_trigger_full_pipeline_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/pipeline",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── Pipeline Refresh (Incremental) ──


@pytest.mark.asyncio
async def test_trigger_incremental_refresh(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_row()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/pipeline/refresh",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "refresh" in resp.json()["message"].lower()


# ── Pipeline Status ──


@pytest.mark.asyncio
async def test_pipeline_status_idle(app_with_mocks):
    app, conn = app_with_mocks
    # site ownership check, crawl_jobs row, pipeline_jobs row
    conn._fetchrow_returns = [_site_exists(), None, None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/pipeline/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


@pytest.mark.asyncio
async def test_pipeline_status_running(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [
        _site_exists(),
        make_record(
            status="clustering",
            started_at=NOW,
            completed_at=None,
            posts_found=100,
            posts_processed=100,
            error=None,
        ),
        None,  # no pipeline_jobs row
    ]
    # has_clusters check
    conn._fetchval_returns = [False]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/pipeline/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_pipeline_status_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/pipeline/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── Cron Endpoints ──


@pytest.mark.asyncio
async def test_cron_daily_refresh_no_secret_dev(app_with_mocks):
    """In dev mode with no cron_secret set, endpoint should still work."""
    app, conn = app_with_mocks

    # Override the verify_cron_secret dependency to allow passthrough
    from app.dependencies import verify_cron_secret
    async def _noop_cron():
        pass
    app.dependency_overrides[verify_cron_secret] = _noop_cron

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/sites/cron/daily-refresh")

    assert resp.status_code == 200
    assert "refresh" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_cron_weekly_recrawl(app_with_mocks):
    app, conn = app_with_mocks

    from app.dependencies import verify_cron_secret
    async def _noop_cron():
        pass
    app.dependency_overrides[verify_cron_secret] = _noop_cron

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/sites/cron/weekly-recrawl")

    assert resp.status_code == 200
    assert "recrawl" in resp.json()["message"].lower() or "re-crawl" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_cron_monthly_reembed(app_with_mocks):
    app, conn = app_with_mocks

    from app.dependencies import verify_cron_secret
    async def _noop_cron():
        pass
    app.dependency_overrides[verify_cron_secret] = _noop_cron

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/sites/cron/monthly-reembed")

    assert resp.status_code == 200
    assert "embed" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_cron_with_valid_secret(app_with_mocks):
    """When cron_secret is set, X-Cron-Secret header must match."""
    app, conn = app_with_mocks

    # Remove any override so the real dependency runs
    from app.dependencies import verify_cron_secret
    app.dependency_overrides.pop(verify_cron_secret, None)

    with patch("app.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.cron_secret = "my-secret-123"
        settings.environment = "production"
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/sites/cron/daily-refresh",
                headers={"X-Cron-Secret": "my-secret-123"},
            )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_cron_with_invalid_secret(app_with_mocks):
    app, conn = app_with_mocks

    from app.dependencies import verify_cron_secret
    app.dependency_overrides.pop(verify_cron_secret, None)

    with patch("app.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.cron_secret = "correct-secret"
        settings.environment = "production"
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/sites/cron/daily-refresh",
                headers={"X-Cron-Secret": "wrong-secret"},
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cron_missing_secret_in_production(app_with_mocks):
    app, conn = app_with_mocks

    from app.dependencies import verify_cron_secret
    app.dependency_overrides.pop(verify_cron_secret, None)

    with patch("app.config.get_settings") as mock_settings:
        settings = MagicMock()
        settings.cron_secret = "my-cron-secret"
        settings.environment = "production"
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/sites/cron/daily-refresh")

    assert resp.status_code == 401
