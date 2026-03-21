"""Integration tests for intelligence endpoints (/v1/sites/{id}/intelligence/*)."""

import pytest
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient, ASGITransport

from tests.conftest import (
    TEST_USER_ID, TEST_SITE_ID, TEST_CLUSTER_ID, TEST_POST_ID_A,
    MockConnection, make_record,
)

AUTH_HEADER = {"Authorization": f"Bearer {TEST_USER_ID}"}
NOW = datetime.now(timezone.utc)
BRIEF_ID = UUID("77777777-8888-9999-aaaa-bbbbbbbbbbbb")


def _site_exists():
    return make_record(id=TEST_SITE_ID)


def _cluster_row():
    return make_record(
        id=TEST_CLUSTER_ID,
        site_id=TEST_SITE_ID,
        label="Python Frameworks",
        description="Posts about Python web frameworks",
        ecosystem_state="swamp",
        health_score=42.5,
        post_count=5,
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


# ── Trigger Clustering ──


@pytest.mark.asyncio
async def test_trigger_clustering_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    # Clear the running pipelines set
    from app.routers.intelligence import _running_pipelines
    _running_pipelines.discard(TEST_SITE_ID)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/cluster",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "Clustering started" in resp.json()["message"]
    _running_pipelines.discard(TEST_SITE_ID)


@pytest.mark.asyncio
async def test_trigger_clustering_already_running(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    from app.routers.intelligence import _running_pipelines
    _running_pipelines.add(TEST_SITE_ID)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/intelligence/cluster",
                headers=AUTH_HEADER,
            )

        assert resp.status_code == 429
    finally:
        _running_pipelines.discard(TEST_SITE_ID)


@pytest.mark.asyncio
async def test_trigger_clustering_site_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/cluster",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── List Clusters ──


@pytest.mark.asyncio
async def test_list_clusters_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]
    conn._fetch_returns = [[_cluster_row()]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/clusters",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["label"] == "Python Frameworks"


@pytest.mark.asyncio
async def test_list_clusters_empty(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]
    conn._fetch_returns = [[]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/clusters",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json() == []


# ── Cluster Detail ──


@pytest.mark.asyncio
async def test_cluster_detail_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists(), _cluster_row()]
    conn._fetch_returns = [[
        make_record(
            post_id=TEST_POST_ID_A,
            title="Best Frameworks",
            url="/best-frameworks",
            composite_score=75.0,
            role="pillar",
            trend="rising",
            traffic_contribution=0.6,
            ranking_strength=0.8,
            internal_link_score=0.5,
        ),
    ]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/clusters/{TEST_CLUSTER_ID}",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["label"] == "Python Frameworks"
    assert len(data["posts"]) == 1
    assert data["posts"][0]["role"] == "pillar"


@pytest.mark.asyncio
async def test_cluster_detail_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists(), None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/clusters/{TEST_CLUSTER_ID}",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


# ── Cannibalization ──


@pytest.mark.asyncio
async def test_detect_cannibalization_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/detect-cannibalization",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert "started" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_list_cannibalization_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]
    conn._fetch_returns = [[]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/cannibalization",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    assert resp.json() == []


# ── Site Health ──


@pytest.mark.asyncio
async def test_site_health_success(app_with_mocks):
    app, conn = app_with_mocks
    # _verify_site, then multiple fetchval/fetchrow/fetch calls
    conn._fetchrow_returns = [_site_exists()]
    # total_posts, role_counts, cannibalistic_posts, avg_health,
    # traffic 30d, 60d, 90d, has_ga4, has_gsc, posts_with_modified, ai_enriched
    conn._fetchval_returns = [
        100,  # total_posts
        0,    # cannibalistic_posts
        65.0, # avg_health
        5000, 10000, 20000,  # traffic 30d, 60d, 90d
        True,  # has_ga4
        False, # has_gsc
        80,    # posts_with_modified
        5,     # ai_enriched
    ]
    conn._fetch_returns = [
        # role_counts
        [make_record(role="pillar", cnt=20), make_record(role="dead_weight", cnt=10)],
        # cluster rows
        [make_record(id=TEST_CLUSTER_ID, label="Tech", ecosystem_state="desert", post_count=15)],
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/health",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_posts"] == 100
    assert data["content_health_score"] == 65.0
    assert len(data["clusters"]) == 1


# ── Consolidation Plans ──


@pytest.mark.asyncio
async def test_list_consolidation_plans(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.services.consolidation.ConsolidationPlanner") as MockPlanner:
        planner = MockPlanner.return_value
        planner.get_plans = AsyncMock(return_value=[
            {
                "cluster_id": str(TEST_CLUSTER_ID),
                "cluster_label": "Python Frameworks",
                "priority_score": 85.0,
                "pillar_post": {
                    "post_id": str(TEST_POST_ID_A),
                    "title": "Best Frameworks",
                    "url": "/best",
                    "composite_score": 80.0,
                },
                "merge_candidates_count": 3,
                "dead_weight_count": 2,
                "estimated_traffic_recovery": 500,
                "estimated_effort": 4.5,
                "is_quick_win": True,
            }
        ])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                f"/v1/sites/{TEST_SITE_ID}/intelligence/consolidation",
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_quick_win"] is True


# ── Oracle ──


@pytest.mark.asyncio
async def test_oracle_check_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.services.stripe_service.StripeService") as MockStripe, \
         patch("app.services.oracle.PrePublishOracle") as MockOracle:
        svc = MockStripe.return_value
        svc.check_usage_limits = AsyncMock(return_value=True)

        oracle = MockOracle.return_value
        oracle.analyze = AsyncMock(return_value={
            "confidence": "high",
            "verdict": "proceed",
            "reasoning": "Unique angle not covered by existing content.",
            "similar_posts": [],
            "cluster_state": "desert",
            "recommendation": "Go ahead and publish.",
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/intelligence/oracle",
                json={"target_keyword": "python async io"},
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "proceed"
    assert data["confidence"] == "high"


@pytest.mark.asyncio
async def test_oracle_check_missing_input(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.services.stripe_service.StripeService") as MockStripe:
        svc = MockStripe.return_value
        svc.check_usage_limits = AsyncMock(return_value=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/intelligence/oracle",
                json={},
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 400
    assert "draft_text or target_keyword" in resp.json()["detail"]


# ── Content Briefs ──


@pytest.mark.asyncio
async def test_create_brief_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    with patch("app.services.content_briefs.ContentBriefGenerator") as MockGen:
        gen = MockGen.return_value
        gen.generate_brief = AsyncMock(return_value={
            "id": str(BRIEF_ID),
            "target_keyword": "async python",
            "suggested_titles": ["Mastering Async Python"],
            "recommended_word_count": 2000,
            "cannibalization_risk": "low",
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/v1/sites/{TEST_SITE_ID}/intelligence/briefs",
                json={"topic": "async python programming"},
                headers=AUTH_HEADER,
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["target_keyword"] == "async python"


@pytest.mark.asyncio
async def test_create_brief_topic_too_short(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/briefs",
            json={"topic": "ab"},
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_briefs_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]
    conn._fetch_returns = [[
        make_record(
            id=BRIEF_ID,
            target_keyword="python async",
            suggested_titles=["Title A"],
            recommended_word_count=2000,
            cannibalization_risk="low",
            content_angle="tutorial",
            difficulty_level="intermediate",
            status="ready",
            created_at=NOW,
        ),
    ]]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/briefs",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["target_keyword"] == "python async"


@pytest.mark.asyncio
async def test_get_brief_detail(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [
        _site_exists(),
        make_record(
            id=BRIEF_ID,
            site_id=TEST_SITE_ID,
            target_keyword="python async",
            secondary_keywords=["asyncio", "concurrency"],
            suggested_titles=["Mastering Async"],
            recommended_word_count=2000,
            outline='[{"h2": "Introduction"}]',
            questions_to_answer=["What is async?"],
            cannibalization_risk="low",
            differentiation_notes="Focus on practical examples",
            avoid_topics=["threading"],
            internal_links_from='[]',
            internal_links_to='[]',
            content_angle="tutorial",
            difficulty_level="intermediate",
            status="ready",
            created_at=NOW,
            updated_at=NOW,
        ),
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/briefs/{BRIEF_ID}",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["target_keyword"] == "python async"
    assert isinstance(data["outline"], list)


@pytest.mark.asyncio
async def test_get_brief_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists(), None]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/briefs/{BRIEF_ID}",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_brief_success(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]
    conn._execute_results = ["DELETE 1"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.delete(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/briefs/{BRIEF_ID}",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_brief_not_found(app_with_mocks):
    app, conn = app_with_mocks
    conn._fetchrow_returns = [_site_exists()]
    conn._execute_results = ["DELETE 0"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.delete(
            f"/v1/sites/{TEST_SITE_ID}/intelligence/briefs/{BRIEF_ID}",
            headers=AUTH_HEADER,
        )

    assert resp.status_code == 404
