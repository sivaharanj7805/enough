"""Integration tests for retention endpoints (reports, impact tracking, steward, billing)."""

import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from tests.conftest import (
    TEST_USER_ID, TEST_SITE_ID, TEST_CLUSTER_ID, TEST_TRACKING_ID,
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


# ── Send Weekly Report ──


@pytest.mark.asyncio
async def test_send_weekly_report(app_with_mocks):
    app, conn = app_with_mocks
    # db.fetch returns sites
    conn._fetch_returns = [[make_record(id=TEST_SITE_ID)]]

    with patch("app.routers.retention.WeeklyReportService") as MockSvc:
        svc = MockSvc.return_value
        svc.send_report = AsyncMock(return_value=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/reports/send-weekly", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "1/1" in resp.json()["message"]


@pytest.mark.asyncio
async def test_send_weekly_report_no_sites(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetch_returns = [[]]

    with patch("app.routers.retention.WeeklyReportService"):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post("/v1/reports/send-weekly", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert "0/0" in resp.json()["message"]


# ── Report History ──


@pytest.mark.asyncio
async def test_get_report_history(app_with_mocks):
    app, conn = app_with_mocks
    # _verify_site
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.retention.WeeklyReportService") as MockSvc:
        svc = MockSvc.return_value
        svc.get_history = AsyncMock(return_value=[
            {
                "id": TEST_TRACKING_ID,
                "site_id": TEST_SITE_ID,
                "subject": "Weekly Report: Week 12",
                "status": "sent",
                "sent_at": NOW,
            }
        ])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/reports/history",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "sent"


@pytest.mark.asyncio
async def test_get_report_history_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/reports/history",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── Start Impact Tracking ──


@pytest.mark.asyncio
async def test_start_impact_tracking(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.retention.ImpactTracker") as MockTracker:
        tracker = MockTracker.return_value
        tracker.start_tracking = AsyncMock(return_value=TEST_TRACKING_ID)
        tracker.get_all_for_site = AsyncMock(return_value=[
            {
                "id": TEST_TRACKING_ID,
                "site_id": TEST_SITE_ID,
                "cluster_id": TEST_CLUSTER_ID,
                "pillar_url": "/best-post",
                "consolidated_urls": ["/old-1", "/old-2"],
                "baseline_traffic": 1000,
                "baseline_avg_position": 8.5,
                "baseline_date": "2025-03-01",
                "latest_traffic": None,
                "latest_avg_position": None,
                "latest_check_date": None,
                "traffic_change_pct": None,
                "status": "tracking",
                "days_since": 0,
            }
        ])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/impact/track",
                json={
                    "cluster_id": str(TEST_CLUSTER_ID),
                    "pillar_url": "/best-post",
                    "consolidated_urls": ["/old-1", "/old-2"],
                },
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["pillar_url"] == "/best-post"
    assert data["status"] == "tracking"


# ── List Impact Trackings ──


@pytest.mark.asyncio
async def test_list_impact_trackings(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.retention.ImpactTracker") as MockTracker:
        tracker = MockTracker.return_value
        tracker.get_all_for_site = AsyncMock(return_value=[])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/impact",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    assert resp.json() == []


# ── Impact Detail ──


@pytest.mark.asyncio
async def test_get_impact_detail(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.retention.ImpactTracker") as MockTracker:
        tracker = MockTracker.return_value
        tracker.get_detail = AsyncMock(return_value={
            "tracking": {
                "id": TEST_TRACKING_ID,
                "site_id": TEST_SITE_ID,
                "cluster_id": TEST_CLUSTER_ID,
                "pillar_url": "/best",
                "consolidated_urls": ["/a", "/b"],
                "baseline_traffic": 500,
                "baseline_avg_position": 10.0,
                "baseline_date": "2025-03-01",
                "latest_traffic": 600,
                "latest_avg_position": 8.0,
                "latest_check_date": "2025-03-15",
                "traffic_change_pct": 20.0,
                "status": "improved",
                "days_since": 14,
            },
            "snapshots": [
                {
                    "snapshot_date": "2025-03-08",
                    "traffic": 550,
                    "avg_position": 9.0,
                    "redirects_working": 2,
                    "milestone": "week-1",
                }
            ],
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/impact/{TEST_TRACKING_ID}",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["tracking"]["traffic_change_pct"] == 20.0
    assert len(data["snapshots"]) == 1


@pytest.mark.asyncio
async def test_get_impact_detail_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.retention.ImpactTracker") as MockTracker:
        tracker = MockTracker.return_value
        tracker.get_detail = AsyncMock(side_effect=ValueError("Not found"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/impact/{TEST_TRACKING_ID}",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 404


# ── Check Impact ──


@pytest.mark.asyncio
async def test_check_impact(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.retention.ImpactTracker") as MockTracker:
        tracker = MockTracker.return_value
        tracker.check_impact = AsyncMock(return_value={
            "traffic_change_pct": 15.0,
            "position_change": -2.0,
            "status": "improved",
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/impact/{TEST_TRACKING_ID}/check",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "improved"


# ── Impact Card ──


@pytest.mark.asyncio
async def test_get_impact_card(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.retention.ImpactTracker") as MockTracker:
        tracker = MockTracker.return_value
        tracker.generate_impact_card = AsyncMock(return_value={
            "tracking_id": TEST_TRACKING_ID,
            "headline": "Traffic up 20%!",
            "pillar_url": "/best-post",
            "days_since": 14,
            "traffic_change": 200,
            "traffic_change_pct": 20.0,
            "posts_consolidated": 3,
            "redirects_working": 2,
            "summary": "Consolidation resulted in 20% traffic increase.",
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/impact/{TEST_TRACKING_ID}/card",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["traffic_change_pct"] == 20.0
    assert "Traffic up" in data["headline"]


@pytest.mark.asyncio
async def test_get_impact_card_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.routers.retention.ImpactTracker") as MockTracker:
        tracker = MockTracker.return_value
        tracker.generate_impact_card = AsyncMock(side_effect=ValueError("Not found"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/impact/{TEST_TRACKING_ID}/card",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 404


# ── Steward Profile ──


@pytest.mark.asyncio
async def test_get_steward_profile(app_with_mocks):
    app, conn = app_with_mocks

    with patch("app.routers.retention.StewardService") as MockSvc:
        svc = MockSvc.return_value
        svc.get_profile = AsyncMock(return_value={
            "user_id": TEST_USER_ID,
            "member_since": "2025-01-01",
            "swamps_cleared": 3,
            "deserts_revived": 1,
            "seedlings_planted": 5,
            "total_posts_consolidated": 15,
            "total_redirects_created": 10,
            "estimated_traffic_recovered": 2500,
            "efficiency_improvement": 12.5,
            "health_improvement": 18.0,
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/v1/profile/steward", headers=AUTH_HEADER)

    assert resp.status_code == 200
    data = resp.json()
    assert data["swamps_cleared"] == 3
    assert data["user_id"] == TEST_USER_ID


@pytest.mark.asyncio
async def test_get_steward_profile_no_auth(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/v1/profile/steward")

    assert resp.status_code == 422
