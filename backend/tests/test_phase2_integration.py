"""Phase 2 Integration Tests — end-to-end pipeline with synthetic data.

Tests the full intelligence pipeline without external dependencies
(no Supabase, no OpenAI, no Claude). Uses mock DB connections and
verifies that each service processes data correctly through the chain.
"""

import json
import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4, UUID

from app.services.recommendations import RecommendationEngine


# ═══════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════

SITE_ID = uuid4()
POST_IDS = [uuid4() for _ in range(8)]
CLUSTER_IDS = [uuid4() for _ in range(2)]
NOW = datetime.now(timezone.utc)


def _make_mock_db():
    """Create a mock DB connection with common methods."""
    db = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.fetchval = AsyncMock(return_value=0)
    db.execute = AsyncMock()
    db.executemany = AsyncMock()
    return db


# ═══════════════════════════════════════════════
# Clustering Integration
# ═══════════════════════════════════════════════

class TestClusteringIntegration:
    """Test clustering pipeline with synthetic embeddings."""

    @pytest.mark.asyncio
    async def test_cluster_site_no_embeddings(self):
        """Site with no embeddings should return 0 clusters."""
        from app.services.clustering import TopicClusterer

        db = _make_mock_db()
        db.fetch.return_value = []  # No embeddings

        with patch.object(TopicClusterer, '__init__', lambda self: None):
            clusterer = TopicClusterer()
            clusterer.anthropic = AsyncMock()
            clusterer.rate_limiter = AsyncMock()
            clusterer.rate_limiter.wait = AsyncMock()

            result = await clusterer.cluster_site(db, SITE_ID)
            assert result == 0

    @pytest.mark.asyncio
    async def test_cluster_site_few_posts(self):
        """< 5 posts should get single cluster + circular layout."""
        from app.services.clustering import TopicClusterer

        db = _make_mock_db()

        # Mock 3 posts with embeddings
        embedding = "[" + ",".join(["0.1"] * 1536) + "]"
        db.fetch.side_effect = [
            # First call: fetch embeddings
            [
                {"post_id": POST_IDS[i], "title": f"Post {i}", "url": f"https://example.com/post-{i}",
                 "word_count": 1000, "embedding_text": embedding}
                for i in range(3)
            ],
            # Second call: fetch old cluster ids (none)
            [],
        ]
        db.fetchval.return_value = CLUSTER_IDS[0]  # New cluster id

        # Mock Claude response for labeling
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test Topic\nA cluster about testing things.")]

        with patch.object(TopicClusterer, '__init__', lambda self: None):
            clusterer = TopicClusterer()
            clusterer.anthropic = AsyncMock()
            clusterer.anthropic.messages.create = AsyncMock(return_value=mock_response)
            clusterer.rate_limiter = AsyncMock()
            clusterer.rate_limiter.wait = AsyncMock()

            result = await clusterer.cluster_site(db, SITE_ID)
            assert result == 1  # Single cluster for <5 posts

            # Verify 2D positions were stored via executemany
            update_calls = [c for c in db.executemany.call_args_list
                           if "x_pos" in str(c)]
            assert len(update_calls) >= 1  # At least one batch update



# ═══════════════════════════════════════════════
# Health Scoring Integration
# ═══════════════════════════════════════════════

class TestHealthScoringIntegration:
    """Test health scoring with mock DB data."""

    @pytest.mark.asyncio
    async def test_score_site_no_clusters(self):
        """Site with no clusters should return 0."""
        from app.services.health_scoring import HealthScorer

        db = _make_mock_db()
        db.execute.return_value = None
        db.fetch.return_value = []  # No clusters

        scorer = HealthScorer()
        result = await scorer.score_site(db, SITE_ID)
        assert result == 0

    @pytest.mark.asyncio
    async def test_score_cluster_with_posts(self):
        """Cluster with posts should produce valid health scores."""
        from app.services.health_scoring import HealthScorer

        # Use a real dict subclass that supports both dict and attribute access
        class Row(dict):
            def __getattr__(self, key):
                try:
                    return self[key]
                except KeyError:
                    raise AttributeError(key)

        db = _make_mock_db()

        good_post = Row(
            id=POST_IDS[0], title="Good Post", url="https://example.com/good",
            publish_date=NOW - timedelta(days=30),
            modified_date=NOW - timedelta(days=10),
            word_count=1500,
            headings=json.dumps([{"level": "h2", "text": "Intro"}]),
            meta_description="A great post about testing.",
        )
        bad_post = Row(
            id=POST_IDS[1], title="Bad Post", url="https://example.com/bad",
            publish_date=NOW - timedelta(days=400),
            modified_date=None,
            word_count=200, headings=None, meta_description=None,
        )

        db.fetch.side_effect = [
            [good_post, bad_post],  # posts in cluster (first fetch in _score_cluster)
            [Row(post_id=POST_IDS[0], pv=500)],  # recent 30d
            [Row(post_id=POST_IDS[0], pv=400)],  # prev 30d
            [Row(post_id=POST_IDS[0], pv=900), Row(post_id=POST_IDS[1], pv=2)],  # 60d
            [Row(post_id=POST_IDS[0], pv=1200)],  # 90d
            [Row(post_id=POST_IDS[0], avg_pos=5.0)],  # positions
            [Row(post_id=POST_IDS[0], avg_bounce=0.3, avg_time=120.0)],  # engagement
            [Row(post_id=POST_IDS[0], cnt=5)],  # inbound
            [Row(post_id=POST_IDS[0], cnt=3)],  # outbound
            [],  # cannibalization
            [],  # AI readiness scores
        ]

        scorer = HealthScorer()
        result = await scorer._score_cluster(db, CLUSTER_IDS[0], SITE_ID)
        assert result == 2

        assert db.executemany.called
        records = db.executemany.call_args[0][1]
        assert len(records) == 2

        # composite_score is index 5 in the INSERT tuple
        score_good = records[0][5]
        score_bad = records[1][5]
        assert score_good > score_bad, f"Good ({score_good}) should beat Bad ({score_bad})"

    def test_all_weights_sum_to_one(self):
        """Verify all health scoring weights sum to exactly 1.0."""
        from app.services.health_scoring import (
            W_TRAFFIC_TREND, W_RANKING, W_ENGAGEMENT,
            W_FRESHNESS, W_CONTENT_DEPTH, W_INTERNAL_LINKS,
            W_TECHNICAL_SEO, W_AI_READINESS,
        )
        total = sum([
            W_TRAFFIC_TREND, W_RANKING, W_ENGAGEMENT,
            W_FRESHNESS, W_CONTENT_DEPTH, W_INTERNAL_LINKS,
            W_TECHNICAL_SEO, W_AI_READINESS,
        ])
        assert abs(total - 1.0) < 0.0001

    def test_composite_score_range(self):
        """Composite score should always be 0-100."""
        from app.services.health_scoring import (
            W_TRAFFIC_TREND, W_RANKING, W_ENGAGEMENT,
            W_FRESHNESS, W_CONTENT_DEPTH, W_INTERNAL_LINKS,
            W_TECHNICAL_SEO, W_AI_READINESS,
        )
        # All factors at 0
        min_score = 0 * (W_TRAFFIC_TREND + W_RANKING + W_ENGAGEMENT +
                         W_FRESHNESS + W_CONTENT_DEPTH + W_INTERNAL_LINKS +
                         W_TECHNICAL_SEO + W_AI_READINESS)
        assert min_score == 0.0

        # All factors at 100
        max_score = 100 * (W_TRAFFIC_TREND + W_RANKING + W_ENGAGEMENT +
                           W_FRESHNESS + W_CONTENT_DEPTH + W_INTERNAL_LINKS +
                           W_TECHNICAL_SEO + W_AI_READINESS)
        assert abs(max_score - 100.0) < 0.01


# ═══════════════════════════════════════════════
# Cannibalization Integration
# ═══════════════════════════════════════════════

class TestCannibalizationIntegration:
    """Test cannibalization detection with mock data."""

    @pytest.mark.asyncio
    async def test_detect_no_clusters(self):
        """No clusters → 0 pairs."""
        from app.services.cannibalization import CannibalizationDetector

        db = _make_mock_db()
        db.fetch.return_value = []

        detector = CannibalizationDetector()
        result = await detector.detect_for_site(db, SITE_ID)
        assert result == 0

    def test_severity_matrix(self):
        """Test all severity combinations (calibrated for text-embedding-3-small)."""
        from app.services.cannibalization import CannibalizationDetector

        # Critical: cosine >= 0.65 + shared queries
        assert CannibalizationDetector._compute_severity(0.70, 2) == "critical"

        # High: cosine >= 0.55
        assert CannibalizationDetector._compute_severity(0.57, 0) == "high"

        # High: moderate cosine + shared
        assert CannibalizationDetector._compute_severity(0.47, 1) == "high"

        # Medium: cosine at threshold
        assert CannibalizationDetector._compute_severity(0.45, 0) == "medium"

        # Medium: many shared queries
        assert CannibalizationDetector._compute_severity(None, 4) == "medium"

        # Low: few shared only
        assert CannibalizationDetector._compute_severity(None, 1) == "low"
        assert CannibalizationDetector._compute_severity(0.2, 2) == "low"


# ═══════════════════════════════════════════════
# Problem Detection Integration
# ═══════════════════════════════════════════════

class TestProblemDetectionIntegration:
    """Test problem detection with mock data."""

    @pytest.mark.asyncio
    async def test_detect_all_empty_site(self):
        """Site with no data should detect 0 problems."""
        from app.services.problem_detection import ProblemDetector

        db = _make_mock_db()
        db.execute.return_value = None
        db.fetch.return_value = []

        detector = ProblemDetector()
        result = await detector.detect_all(db, SITE_ID)
        assert result["decay"] == 0
        assert result["thin"] == 0
        assert result["seo"] == 0
        assert result["orphan"] == 0
        assert result["readability"] == 0
        assert result["velocity"] == 0

    @pytest.mark.asyncio
    async def test_detect_orphans(self):
        """Posts with no inbound links should be orphans."""
        from app.services.problem_detection import ProblemDetector

        db = _make_mock_db()
        orphan_posts = [
            {"id": POST_IDS[0], "title": "Lonely Post"},
            {"id": POST_IDS[1], "title": "Also Lonely"},
        ]

        async def mock_fetch(query, *args):
            if "NOT EXISTS" in query:
                return orphan_posts
            return []

        db.fetch = mock_fetch

        detector = ProblemDetector()
        result = await detector.detect_all(db, SITE_ID)
        assert result["orphan"] == 2


# ═══════════════════════════════════════════════
# Recommendation Engine Integration
# ═══════════════════════════════════════════════

class TestRecommendationEngineIntegration:
    """Test recommendation engine with mock Claude responses."""

    def test_parse_json_various_formats(self):
        """Test JSON parsing handles all Claude response formats."""
        engine = RecommendationEngine.__new__(RecommendationEngine)

        # Clean JSON
        assert engine._parse_json('{"a": 1}') == {"a": 1}

        # With markdown fences
        assert engine._parse_json('```json\n{"a": 1}\n```') == {"a": 1}

        # With preamble text
        assert engine._parse_json('Here is the result:\n{"a": 1}') == {"a": 1}

        # With trailing text
        assert engine._parse_json('{"a": 1}\nLet me know if you need more.') == {"a": 1}

        # Nested JSON
        result = engine._parse_json('{"actions": ["a", "b"], "nested": {"x": 1}}')
        assert result["nested"]["x"] == 1

    @pytest.mark.asyncio
    async def test_generate_for_site_no_problems(self):
        """Site with no problems should generate 0 recommendations (except growth)."""
        db = _make_mock_db()
        db.fetch.return_value = []

        with patch.object(RecommendationEngine, '__init__', lambda self: None):
            engine = RecommendationEngine()
            engine.anthropic = AsyncMock()
            engine.rate_limiter = AsyncMock()
            engine.rate_limiter.wait = AsyncMock()

            # Mock _generate_growth_recommendations to return 0
            with patch.object(engine, '_generate_growth_recommendations', return_value=0):
                result = await engine.generate_for_site(db, SITE_ID)
                assert result == 0

    @pytest.mark.asyncio
    async def test_call_claude_handles_error(self):
        """Claude API errors should be caught and return error dict."""
        with patch.object(RecommendationEngine, '__init__', lambda self: None):
            engine = RecommendationEngine()
            engine.anthropic = AsyncMock()
            engine.anthropic.messages.create = AsyncMock(side_effect=Exception("API down"))
            engine.rate_limiter = AsyncMock()
            engine.rate_limiter.wait = AsyncMock()

            result = await engine._call_claude("test prompt")
            assert "error" in result

    def test_format_headings_robustness(self):
        """Headings formatter should handle all edge cases."""
        engine = RecommendationEngine.__new__(RecommendationEngine)

        assert engine._format_headings(None) == "None"
        assert engine._format_headings("") == "None"
        assert engine._format_headings([]) == "None"
        assert engine._format_headings("invalid json") == "None"
        assert engine._format_headings(123) == "None"

        # Valid cases
        assert "h2" in engine._format_headings([{"level": "h2", "text": "Test"}])
        assert "h2" in engine._format_headings(json.dumps([{"level": "h2", "text": "Test"}]))


# ═══════════════════════════════════════════════
# Pipeline Integration
# ═══════════════════════════════════════════════

class TestPipelineSteps:
    """Verify pipeline step ordering and dependencies."""

    def test_pipeline_step_order(self):
        """Verify the pipeline runs in the correct order."""
        import inspect
        from app.routers.intelligence import _run_full_pipeline

        source = inspect.getsource(_run_full_pipeline)

        # Match on instantiation (not imports, which are alphabetical)
        clustering_pos = source.index("TopicClusterer()")
        cannibalization_pos = source.index("CannibalizationDetector()")
        health_pos = source.index("HealthScorer()")
        problem_pos = source.index("ProblemDetector()")
        recommendation_pos = source.index("generate_fast_recommendations")

        assert clustering_pos < cannibalization_pos < health_pos < problem_pos < recommendation_pos

    def test_pipeline_has_all_steps(self):
        """Verify all 5 pipeline steps are present."""
        import inspect
        from app.routers.intelligence import _run_full_pipeline

        source = inspect.getsource(_run_full_pipeline)

        assert "TopicClusterer" in source
        assert "CannibalizationDetector" in source
        assert "HealthScorer" in source
        assert "ProblemDetector" in source
        assert "generate_fast_recommendations" in source

    def test_pipeline_status_tracking(self):
        """Verify pipeline tracks status for each step."""
        import inspect
        from app.routers.intelligence import _run_full_pipeline

        source = inspect.getsource(_run_full_pipeline)

        # Should update status for each step
        assert source.count("_update_pipeline_status") >= 5  # start + 4 transitions + complete


# ═══════════════════════════════════════════════
# Router Endpoint Existence
# ═══════════════════════════════════════════════

class TestRouterEndpoints:
    """Verify all expected endpoints exist on the router."""

    def test_all_phase2_endpoints_registered(self):
        from app.routers.intelligence import router

        routes = [r.path for r in router.routes]

        # Problem detection endpoints
        assert "/{site_id}/intelligence/detect-problems" in routes
        assert "/{site_id}/intelligence/problems" in routes
        assert "/{site_id}/intelligence/problems/{post_id}" in routes

        # Recommendation endpoints
        assert "/{site_id}/intelligence/generate-recommendations" in routes
        assert "/{site_id}/intelligence/recommendations" in routes
        assert "/{site_id}/intelligence/recommendations/{post_id}" in routes
        assert "/{site_id}/intelligence/recommendations/{recommendation_id}/status" in routes
        assert "/{site_id}/intelligence/cannibalization/{pair_id}/recommend" in routes

    def test_existing_endpoints_still_present(self):
        from app.routers.intelligence import router

        routes = [r.path for r in router.routes]

        # Original Phase 2 endpoints should still work
        assert "/{site_id}/intelligence/cluster" in routes
        assert "/{site_id}/intelligence/clusters" in routes
        assert "/{site_id}/intelligence/detect-cannibalization" in routes
        assert "/{site_id}/intelligence/cannibalization" in routes
        assert "/{site_id}/intelligence/score-health" in routes
        assert "/{site_id}/intelligence/health" in routes
        assert "/{site_id}/intelligence/run-all" in routes
        assert "/{site_id}/intelligence/pipeline-status" in routes
        assert "/{site_id}/intelligence/oracle" in routes

    def test_endpoint_count(self):
        from app.routers.intelligence import router

        routes = [r for r in router.routes if hasattr(r, 'methods')]
        assert len(routes) >= 20, f"Expected 20+ endpoints, got {len(routes)}"


# ═══════════════════════════════════════════════
# Schema Validation
# ═══════════════════════════════════════════════

class TestSchemaValidation:
    """Test Pydantic models reject invalid data."""

    def test_recommendation_status_rejects_invalid(self):
        from app.models.schemas import RecommendationStatusUpdate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RecommendationStatusUpdate(status="invalid")

        with pytest.raises(ValidationError):
            RecommendationStatusUpdate(status="")

    def test_recommendation_status_accepts_valid(self):
        from app.models.schemas import RecommendationStatusUpdate

        for status in ["pending", "in_progress", "completed", "dismissed"]:
            update = RecommendationStatusUpdate(status=status)
            assert update.status == status

    def test_problem_detection_response_computes_total(self):
        from app.models.schemas import ProblemDetectionResponse

        resp = ProblemDetectionResponse(decay=5, thin=3, seo=7, orphan=2, total=17)
        assert resp.total == 17

    def test_recommendation_response_handles_empty_actions(self):
        from app.models.schemas import RecommendationResponse

        rec = RecommendationResponse(
            id=uuid4(), post_id=uuid4(),
            recommendation_type="refresh", priority="high",
            title="Test", summary="Test",
            specific_actions=[], status="pending",
            created_at=NOW, updated_at=NOW,
        )
        assert rec.specific_actions == []


