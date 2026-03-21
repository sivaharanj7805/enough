"""Integration tests for action layer endpoints (narratives, calendar, redirects)."""

import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from tests.conftest import (
    TEST_USER_ID, TEST_SITE_ID, TEST_CLUSTER_ID,
    MockConnection, make_record,
)

AUTH_HEADER = {"Authorization": f"Bearer {TEST_USER_ID}"}
NOW = datetime.now(timezone.utc)


def _site_exists():
    return make_record(id=TEST_SITE_ID)


def _cluster_exists():
    return make_record(id=TEST_CLUSTER_ID)


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


# ── Get Cluster Narrative ──


@pytest.mark.asyncio
async def test_get_cluster_narrative_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists(), _cluster_exists()]

    with patch("app.services.ecosystem_voice.EcosystemVoice") as MockVoice:
        voice = MockVoice.return_value
        voice.get_narrative = AsyncMock(return_value={
            "cluster_id": TEST_CLUSTER_ID,
            "narrative_text": "This cluster is a swamp. Too many overlapping articles...",
            "generated_at": NOW,
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/intelligence/clusters/{TEST_CLUSTER_ID}/narrative",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "swamp" in data["narrative_text"]


@pytest.mark.asyncio
async def test_get_cluster_narrative_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists(), _cluster_exists()]

    with patch("app.services.ecosystem_voice.EcosystemVoice") as MockVoice:
        voice = MockVoice.return_value
        voice.get_narrative = AsyncMock(return_value=None)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/intelligence/clusters/{TEST_CLUSTER_ID}/narrative",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_narrative_cluster_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists(), None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/clusters/{TEST_CLUSTER_ID}/narrative",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── Trigger Narrative Generation ──


@pytest.mark.asyncio
async def test_trigger_narrative_generation(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/narratives/generate",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "Narrative generation started" in resp.json()["message"]


@pytest.mark.asyncio
async def test_trigger_narrative_no_auth(app_with_mocks):
    app, conn = app_with_mocks

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/narratives/generate",
        )

    assert resp.status_code == 422


# ── Get Calendar ──


@pytest.mark.asyncio
async def test_get_calendar_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.services.calendar_restraint.CalendarRestraint") as MockCal:
        cal = MockCal.return_value
        cal.get_recommendations = AsyncMock(return_value={
            "site_id": TEST_SITE_ID,
            "recommendations": [
                {
                    "cluster_id": TEST_CLUSTER_ID,
                    "cluster_label": "Python Frameworks",
                    "ecosystem_state": "swamp",
                    "recommendation_type": "pause",
                    "recommendation_text": "Pause publishing in this topic.",
                    "suggested_keywords": None,
                    "pause_months": 3,
                }
            ],
            "summary": "1 cluster needs attention.",
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/intelligence/calendar",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["recommendation_type"] == "pause"


# ── Trigger Calendar Generation ──


@pytest.mark.asyncio
async def test_trigger_calendar_generation(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/calendar/generate",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "Calendar" in resp.json()["message"]


# ── Push Redirects ──


@pytest.mark.asyncio
async def test_push_redirects_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.services.redirect_push.RedirectPusher") as MockPusher:
        pusher = MockPusher.return_value
        pusher.push_redirects = AsyncMock(return_value={
            "site_id": TEST_SITE_ID,
            "entries": [
                {
                    "old_url": "/old-post",
                    "new_url": "/new-post",
                    "status": "pushed",
                    "pushed_at": NOW,
                    "verified_at": None,
                    "error": None,
                }
            ],
            "total": 1,
            "pushed": 1,
            "verified": 0,
            "failed": 0,
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/redirects/push",
                json={
                    "redirect_map": [
                        {"old_url": "/old-post", "new_url": "/new-post"},
                    ]
                },
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["pushed"] == 1
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_push_redirects_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/redirects/push",
            json={"redirect_map": [{"old_url": "/a", "new_url": "/b"}]},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── Get Redirect Status ──


@pytest.mark.asyncio
async def test_get_redirect_status(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.services.redirect_push.RedirectPusher") as MockPusher:
        pusher = MockPusher.return_value
        pusher.get_status = AsyncMock(return_value={
            "site_id": TEST_SITE_ID,
            "entries": [],
            "total": 0,
            "pushed": 0,
            "verified": 0,
            "failed": 0,
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/redirects/status",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ── Verify Redirects ──


@pytest.mark.asyncio
async def test_verify_redirects(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.services.redirect_push.RedirectPusher") as MockPusher:
        pusher = MockPusher.return_value
        pusher.verify_redirects = AsyncMock(return_value={
            "site_id": TEST_SITE_ID,
            "entries": [
                {
                    "old_url": "/old",
                    "new_url": "/new",
                    "status": "verified",
                    "pushed_at": NOW,
                    "verified_at": NOW,
                    "error": None,
                }
            ],
            "total": 1,
            "pushed": 1,
            "verified": 1,
            "failed": 0,
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/redirects/verify",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    assert resp.json()["verified"] == 1
