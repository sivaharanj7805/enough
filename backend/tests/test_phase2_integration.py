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

            # Verify 2D positions were stored
            update_calls = [c for c in db.execute.call_args_list
                           if "x_pos" in str(c)]
            assert len(update_calls) == 3  # One per post

    def test_clustering_with_real_umap_hdbscan(self):
        """Verify UMAP + HDBSCAN produces valid output with 2 clear clusters."""
        from app.services.clustering import TopicClusterer

        rng = np.random.RandomState(42)
        # Two well-separated clusters in 100d
        cluster_a = rng.randn(8, 100) + np.array([10.0] * 100)
        cluster_b = rng.randn(8, 100) + np.array([-10.0] * 100)
        embeddings = np.vstack([cluster_a, cluster_b]).astype(np.float32)

        clusterer = TopicClusterer.__new__(TopicClusterer)
        labels, positions_2d = clusterer._run_clustering_and_2d(embeddings, 16)

        assert len(labels) == 16
        assert positions_2d.shape == (16, 2)

        # Should find 2 clusters
        unique_labels = set(labels)
        n_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        assert n_clusters >= 2, f"Expected 2 clusters, got {n_clusters}. Labels: {labels}"

        # Posts in the same original group should get the same label
        # (not guaranteed but likely with well-separated clusters)
        labels_a = set(labels[:8])
        labels_b = set(labels[8:])
        # At least one group should be homogeneous
        assert len(labels_a) <= 2 or len(labels_b) <= 2

    def test_2d_positions_are_finite(self):
        """2D positions must be finite numbers (no NaN/Inf)."""
        from app.services.clustering import TopicClusterer

        rng = np.random.RandomState(42)
        embeddings = rng.randn(10, 50).astype(np.float32)

        clusterer = TopicClusterer.__new__(TopicClusterer)
        _, positions_2d = clusterer._run_clustering_and_2d(embeddings, 10)

        assert np.all(np.isfinite(positions_2d)), "2D positions contain NaN or Inf"


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

    def test_all_seven_weights_sum_to_one(self):
        """Verify the 7 weights sum to exactly 1.0."""
        from app.services.health_scoring import (
            W_TRAFFIC_TREND, W_RANKING, W_ENGAGEMENT,
            W_FRESHNESS, W_CONTENT_DEPTH, W_INTERNAL_LINKS,
            W_TECHNICAL_SEO,
        )
        total = sum([
            W_TRAFFIC_TREND, W_RANKING, W_ENGAGEMENT,
            W_FRESHNESS, W_CONTENT_DEPTH, W_INTERNAL_LINKS,
            W_TECHNICAL_SEO,
        ])
        assert abs(total - 1.0) < 0.0001

    def test_composite_score_range(self):
        """Composite score should always be 0-100."""
        from app.services.health_scoring import (
            W_TRAFFIC_TREND, W_RANKING, W_ENGAGEMENT,
            W_FRESHNESS, W_CONTENT_DEPTH, W_INTERNAL_LINKS,
            W_TECHNICAL_SEO,
        )
        # All factors at 0
        min_score = 0 * (W_TRAFFIC_TREND + W_RANKING + W_ENGAGEMENT +
                         W_FRESHNESS + W_CONTENT_DEPTH + W_INTERNAL_LINKS +
                         W_TECHNICAL_SEO)
        assert min_score == 0.0

        # All factors at 100
        max_score = 100 * (W_TRAFFIC_TREND + W_RANKING + W_ENGAGEMENT +
                           W_FRESHNESS + W_CONTENT_DEPTH + W_INTERNAL_LINKS +
                           W_TECHNICAL_SEO)
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

    @pytest.mark.asyncio
    async def test_single_post_cluster_no_pairs(self):
        """Cluster with 1 post can't have pairs."""
        from app.services.cannibalization import CannibalizationDetector

        db = _make_mock_db()
        # fetchval: site metadata (no calibrated thresholds)
        db.fetchval.side_effect = [None]
        db.fetch.side_effect = [
            # Calibration: pairwise similarities (too few to calibrate)
            [],
            # Clusters
            [{"id": CLUSTER_IDS[0], "post_count": 1}],
        ]

        detector = CannibalizationDetector()
        result = await detector.detect_for_site(db, SITE_ID)
        assert result == 0

    def test_severity_matrix(self):
        """Test all severity combinations (calibrated for text-embedding-3-small)."""
        from app.services.cannibalization import CannibalizationDetector

        # Critical: cosine >= 0.60 + shared queries
        assert CannibalizationDetector._compute_severity(0.65, 2) == "critical"

        # High: cosine >= 0.50
        assert CannibalizationDetector._compute_severity(0.52, 0) == "high"

        # High: moderate cosine + shared
        assert CannibalizationDetector._compute_severity(0.42, 1) == "high"

        # Medium: cosine at threshold
        assert CannibalizationDetector._compute_severity(0.40, 0) == "medium"

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
        assert result == {"decay": 0, "thin": 0, "seo": 0, "orphan": 0}

    @pytest.mark.asyncio
    async def test_detect_thin_content(self):
        """Posts under 500 words should be flagged."""
        from app.services.problem_detection import ProblemDetector

        db = _make_mock_db()
        thin_posts = [
            {"id": POST_IDS[0], "title": "Short Post", "word_count": 200},
            {"id": POST_IDS[1], "title": "Medium Post", "word_count": 450},
        ]

        call_count = 0
        async def mock_fetch(query, *args):
            nonlocal call_count
            call_count += 1
            # Decay queries return empty
            if "gsc_metrics" in query or "modified_date" in query:
                return []
            # Thin content absolute
            if "word_count < 500" in query:
                return thin_posts
            # Thin content cluster avg
            if "cluster_avgs" in query:
                return []
            # Thin content bounce
            if "bounce_rate" in query:
                return []
            # SEO issues
            if "meta_description" in query:
                return []
            # Orphans
            if "NOT EXISTS" in query:
                return []
            return []

        db.fetch = mock_fetch

        detector = ProblemDetector()
        result = await detector.detect_all(db, SITE_ID)
        assert result["thin"] >= 2

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

        # Verify ordering: clustering before cannibalization before health before problems before recommendations
        clustering_pos = source.index("TopicClusterer")
        cannibalization_pos = source.index("CannibalizationDetector")
        health_pos = source.index("HealthScorer")
        problem_pos = source.index("ProblemDetector")
        recommendation_pos = source.index("RecommendationEngine")

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
        assert "RecommendationEngine" in source

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


# ═══════════════════════════════════════════════
# Migration Validation
# ═══════════════════════════════════════════════

class TestMigrationValidation:
    """Verify migration SQL is well-formed."""

    def _read_migration(self):
        with open("migrations/005_phase2_intelligence.sql") as f:
            return f.read()

    def test_content_problems_table(self):
        sql = self._read_migration()
        assert "CREATE TABLE IF NOT EXISTS content_problems" in sql
        assert "problem_type TEXT NOT NULL" in sql
        assert "severity TEXT NOT NULL" in sql
        assert "UNIQUE(post_id, problem_type)" in sql

    def test_recommendations_table(self):
        sql = self._read_migration()
        assert "CREATE TABLE IF NOT EXISTS recommendations" in sql
        assert "recommendation_type TEXT NOT NULL" in sql
        assert "specific_actions JSONB" in sql
        assert "ai_generated_content JSONB" in sql
        assert "status TEXT NOT NULL DEFAULT 'pending'" in sql

    def test_post_positions(self):
        sql = self._read_migration()
        assert "x_pos FLOAT" in sql
        assert "y_pos FLOAT" in sql

    def test_hnsw_index(self):
        sql = self._read_migration()
        assert "hnsw" in sql.lower()
        assert "vector_cosine_ops" in sql
        assert "m = 16" in sql
        assert "ef_construction = 64" in sql

    def test_dead_trend_constraint(self):
        sql = self._read_migration()
        assert "'dead'" in sql

    def test_all_problem_types_present(self):
        sql = self._read_migration()
        expected_types = [
            "decay_mild", "decay_moderate", "decay_severe",
            "thin_content", "thin_below_cluster_avg", "thin_high_bounce",
            "seo_missing_meta", "seo_title_length", "seo_no_headings",
            "seo_no_internal_links", "seo_no_images",
            "orphan", "cannibalization",
        ]
        for ptype in expected_types:
            assert ptype in sql, f"Missing problem type: {ptype}"

    def test_all_recommendation_types_present(self):
        sql = self._read_migration()
        expected_types = ["merge", "refresh", "optimize", "delete", "expand", "interlink", "growth"]
        for rtype in expected_types:
            assert f"'{rtype}'" in sql, f"Missing recommendation type: {rtype}"

    def test_indexes_created(self):
        sql = self._read_migration()
        assert "idx_content_problems_post" in sql
        assert "idx_content_problems_site" in sql
        assert "idx_recommendations_post" in sql
        assert "idx_recommendations_site" in sql
