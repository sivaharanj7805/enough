"""Integration tests for Google OAuth + GSC/GA4 sync endpoints."""

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


# ── Google Connect (start OAuth) ──


@pytest.mark.asyncio
async def test_google_connect_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.google_integration.get_auth_url", return_value="https://accounts.google.com/o/oauth2/v2/auth?client_id=test"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/google/connect",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "auth_url" in data
    assert "google" in data["auth_url"].lower()


@pytest.mark.asyncio
async def test_google_connect_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/google/connect",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── Google Disconnect ──


@pytest.mark.asyncio
async def test_google_disconnect_success(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.delete(
            f"/v1/sites/{TEST_SITE_ID}/google/disconnect",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json()["disconnected"] is True


# ── Google Status ──


@pytest.mark.asyncio
async def test_google_status_connected(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [make_record(
        google_tokens="encrypted-tokens",
        gsc_site_url="https://example.com/",
        ga4_property_id="properties/12345",
        last_gsc_sync=NOW,
        last_ga4_sync=NOW,
    )]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/google/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["gsc_site_url"] == "https://example.com/"


@pytest.mark.asyncio
async def test_google_status_not_connected(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [make_record(
        google_tokens=None,
        gsc_site_url=None,
        ga4_property_id=None,
        last_gsc_sync=None,
        last_ga4_sync=None,
    )]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/google/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json()["connected"] is False


@pytest.mark.asyncio
async def test_google_status_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/google/status",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── GSC Sync ──


@pytest.mark.asyncio
async def test_gsc_sync_success(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.GSCSyncService") as MockGSC:
        svc = MockGSC.return_value
        svc.sync_site = AsyncMock(return_value={
            "status": "ok",
            "rows_synced": 150,
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/gsc/sync",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    assert resp.json()["rows_synced"] == 150


@pytest.mark.asyncio
async def test_gsc_sync_error(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.GSCSyncService") as MockGSC:
        svc = MockGSC.return_value
        svc.sync_site = AsyncMock(return_value={"error": "Google account not connected"})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/gsc/sync",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 400


# ── GSC Sites List ──


@pytest.mark.asyncio
async def test_list_gsc_sites(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.get_valid_token", new_callable=AsyncMock) as mock_token, \
         patch("app.routers.google_integration.GSCSyncService") as MockGSC:
        mock_token.return_value = "valid-access-token"
        svc = MockGSC.return_value
        svc.list_gsc_sites = AsyncMock(return_value=[
            {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"},
        ])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/gsc/sites",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    assert len(resp.json()["sites"]) == 1


@pytest.mark.asyncio
async def test_list_gsc_sites_not_connected(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.get_valid_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/gsc/sites",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 400


# ── Set GSC Site URL ──


@pytest.mark.asyncio
async def test_set_gsc_site_url(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(
            f"/v1/sites/{TEST_SITE_ID}/gsc/site-url",
            json={"gsc_site_url": "https://example.com/"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json()["gsc_site_url"] == "https://example.com/"


# ── GA4 Sync ──


@pytest.mark.asyncio
async def test_ga4_sync_success(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.GA4SyncService") as MockGA4:
        svc = MockGA4.return_value
        svc.sync_site = AsyncMock(return_value={
            "status": "ok",
            "rows_synced": 200,
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/ga4/sync",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    assert resp.json()["rows_synced"] == 200


@pytest.mark.asyncio
async def test_ga4_sync_error(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.GA4SyncService") as MockGA4:
        svc = MockGA4.return_value
        svc.sync_site = AsyncMock(return_value={"error": "No GA4 property configured"})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/ga4/sync",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 400


# ── GA4 Properties List ──


@pytest.mark.asyncio
async def test_list_ga4_properties(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.get_valid_token", new_callable=AsyncMock) as mock_token, \
         patch("app.routers.google_integration.GA4SyncService") as MockGA4:
        mock_token.return_value = "valid-access-token"
        svc = MockGA4.return_value
        svc.list_ga4_properties = AsyncMock(return_value=[
            {"name": "properties/12345", "displayName": "My Site"},
        ])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/ga4/properties",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    assert len(resp.json()["properties"]) == 1


@pytest.mark.asyncio
async def test_list_ga4_properties_not_connected(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.get_valid_token", new_callable=AsyncMock) as mock_token:
        mock_token.return_value = None

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/ga4/properties",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 400


# ── Set GA4 Property ID ──


@pytest.mark.asyncio
async def test_set_ga4_property_id(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.patch(
            f"/v1/sites/{TEST_SITE_ID}/ga4/property-id",
            json={"property_id": "properties/12345"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json()["property_id"] == "properties/12345"


# ── Sync All ──


@pytest.mark.asyncio
async def test_sync_all_google_data(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.google_integration.GSCSyncService") as MockGSC, \
         patch("app.routers.google_integration.GA4SyncService") as MockGA4:
        MockGSC.return_value.sync_site = AsyncMock(return_value={"status": "ok", "rows_synced": 100})
        MockGA4.return_value.sync_site = AsyncMock(return_value={"status": "ok", "rows_synced": 200})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/google/sync-all",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["gsc"]["rows_synced"] == 100
    assert data["ga4"]["rows_synced"] == 200


@pytest.mark.asyncio
async def test_google_endpoints_no_auth(app_with_mocks):
    """All Google endpoints require auth."""
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(f"/v1/sites/{TEST_SITE_ID}/google/connect")
        assert resp.status_code == 422

        resp = await ac.delete(f"/v1/sites/{TEST_SITE_ID}/google/disconnect")
        assert resp.status_code == 422

        resp = await ac.get(f"/v1/sites/{TEST_SITE_ID}/google/status")
        assert resp.status_code == 422
