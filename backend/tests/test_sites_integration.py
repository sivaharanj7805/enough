"""Integration tests for sites endpoints (/v1/sites/*)."""

import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from tests.conftest import TEST_USER_ID, TEST_SITE_ID, MockConnection, make_record

AUTH_HEADER = {"Authorization": f"Bearer {TEST_USER_ID}"}

NOW = datetime.now(timezone.utc)

SITE_ROW = make_record(
    id=TEST_SITE_ID,
    user_id=UUID(TEST_USER_ID),
    name="My Blog",
    domain="example.com",
    cms_type="wordpress",
    wordpress_url="https://example.com/wp-json",
    wordpress_app_password=None,
    sitemap_url=None,
    ga4_property_id=None,
    gsc_site_url=None,
    google_tokens=None,
    last_crawl_at=None,
    last_analytics_sync_at=None,
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


# ── Create Site ──


@pytest.mark.asyncio
async def test_create_site_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [SITE_ROW]
    # Mock the subscription guard (require_site_limit)
    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.check_usage_limits = AsyncMock(return_value=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/sites", json={
                "name": "My Blog",
                "domain": "example.com",
                "cms_type": "wordpress",
            }, headers=AUTH_HEADER)

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Blog"
    assert data["domain"] == "example.com"


@pytest.mark.asyncio
async def test_create_site_ssrf_blocked(app_with_mocks):
    app, conn = app_with_mocks
    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.check_usage_limits = AsyncMock(return_value=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/sites", json={
                "name": "Evil Site",
                "domain": "evil.com",
                "cms_type": "wordpress",
                "wordpress_url": "http://localhost:8080/wp-json",
            }, headers=AUTH_HEADER)

    assert resp.status_code == 422
    assert "localhost" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_site_no_auth(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/v1/sites", json={
            "name": "Test",
            "domain": "test.com",
            "cms_type": "sitemap",
        })

    assert resp.status_code == 422


# ── List Sites ──


@pytest.mark.asyncio
async def test_list_sites_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetch_returns = [[SITE_ROW]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/v1/sites", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["sites"]) == 1


@pytest.mark.asyncio
async def test_list_sites_empty(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetch_returns = [[]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/v1/sites", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ── Get Single Site ──


@pytest.mark.asyncio
async def test_get_site_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [SITE_ROW]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/sites/{TEST_SITE_ID}", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["id"] == str(TEST_SITE_ID)


@pytest.mark.asyncio
async def test_get_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/sites/{TEST_SITE_ID}", headers=AUTH_HEADER)

    assert resp.status_code == 404


# ── Delete Site ──


@pytest.mark.asyncio
async def test_delete_site_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._execute_results = ["DELETE 1"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.delete(f"/v1/sites/{TEST_SITE_ID}", headers=AUTH_HEADER)

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._execute_results = ["DELETE 0"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.delete(f"/v1/sites/{TEST_SITE_ID}", headers=AUTH_HEADER)

    assert resp.status_code == 404


# ── Update Site Settings ──


@pytest.mark.asyncio
async def test_update_site_settings_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [make_record(id=TEST_SITE_ID)]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(f"/v1/sites/{TEST_SITE_ID}/settings", json={
            "cms_type": "sitemap",
            "recrawl_schedule": "weekly",
        }, headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "updated" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_update_site_settings_invalid_cms(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [make_record(id=TEST_SITE_ID)]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(f"/v1/sites/{TEST_SITE_ID}/settings", json={
            "cms_type": "invalid_cms",
        }, headers=AUTH_HEADER)

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_site_settings_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(f"/v1/sites/{TEST_SITE_ID}/settings", json={
            "cms_type": "wordpress",
        }, headers=AUTH_HEADER)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_site_settings_no_changes(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [make_record(id=TEST_SITE_ID)]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(f"/v1/sites/{TEST_SITE_ID}/settings", json={}, headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "No changes" in resp.json()["message"]


# ── Update Notification Settings ──


@pytest.mark.asyncio
async def test_update_notification_settings_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [make_record(id=TEST_SITE_ID)]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(f"/v1/sites/{TEST_SITE_ID}/notifications", json={
            "digest_frequency": "weekly",
        }, headers=AUTH_HEADER)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_notification_settings_invalid_frequency(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [make_record(id=TEST_SITE_ID)]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(f"/v1/sites/{TEST_SITE_ID}/notifications", json={
            "digest_frequency": "daily",
        }, headers=AUTH_HEADER)

    assert resp.status_code == 422


# ── Store Google Token ──


@pytest.mark.asyncio
async def test_store_google_token_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._execute_results = ["UPDATE 1"]

    with patch("app.routers.sites.encrypt_value", return_value="encrypted-token"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(f"/v1/sites/{TEST_SITE_ID}/google-token", json={
                "refresh_token": "ya29.my-refresh-token",
            }, headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "stored" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_store_google_token_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._execute_results = ["UPDATE 0"]

    with patch("app.routers.sites.encrypt_value", return_value="encrypted"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(f"/v1/sites/{TEST_SITE_ID}/google-token", json={
                "refresh_token": "ya29.some-token",
            }, headers=AUTH_HEADER)

    assert resp.status_code == 404
