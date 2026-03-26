"""Tests for Phase 2 Intelligence Engine — problem detection, recommendations, clustering."""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.problem_detection import ProblemDetector
from app.services.recommendations import RecommendationEngine
from app.services.clustering import TopicClusterer, _parse_pgvector


def _has_umap():
    try:
        import umap  # noqa: F401
        import hdbscan  # noqa: F401
        return True
    except ImportError:
        return False


# ═══════════════════════════════════════════════
# Clustering
# ═══════════════════════════════════════════════

class TestClusteringHelpers:
    """Test clustering utility functions."""

    def test_parse_pgvector_brackets(self):
        result = _parse_pgvector("[1.0,2.0,3.0]")
        assert result == [1.0, 2.0, 3.0]

    def test_parse_pgvector_no_brackets(self):
        result = _parse_pgvector("1.0,2.0,3.0")
        assert result == [1.0, 2.0, 3.0]

    def test_simple_2d_layout(self):
        clusterer = TopicClusterer.__new__(TopicClusterer)
        positions = clusterer._simple_2d_layout(4)
        assert positions.shape == (4, 2)
        # First point should be at angle 0 → (2.0, 0.0)
        assert abs(positions[0, 0] - 2.0) < 0.01
        assert abs(positions[0, 1] - 0.0) < 0.01

    def test_simple_2d_layout_single_post(self):
        clusterer = TopicClusterer.__new__(TopicClusterer)
        positions = clusterer._simple_2d_layout(1)
        assert positions.shape == (1, 2)

    def test_umap_components_constant(self):
        from app.services.clustering import UMAP_N_COMPONENTS_CLUSTER
        assert UMAP_N_COMPONENTS_CLUSTER == 15  # Research-informed

    @pytest.mark.skipif(
        not _has_umap(),
        reason="umap-learn not installed",
    )
    def test_run_clustering_and_2d(self):
        """Test actual UMAP + HDBSCAN pipeline with small dataset."""
        import numpy as np
        clusterer = TopicClusterer.__new__(TopicClusterer)

        # Create 10 synthetic embeddings in 2 clear clusters
        rng = np.random.RandomState(42)
        cluster_a = rng.randn(5, 50) + np.array([5.0] * 50)
        cluster_b = rng.randn(5, 50) + np.array([-5.0] * 50)
        embeddings = np.vstack([cluster_a, cluster_b]).astype(np.float32)

        labels, positions_2d = clusterer._run_clustering_and_2d(embeddings, 10)
        assert len(labels) == 10
        assert positions_2d.shape == (10, 2)
        # Should find at least 1 cluster (2 ideally)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        assert n_clusters >= 1


# ═══════════════════════════════════════════════
# Problem Detection
# ═══════════════════════════════════════════════

class TestProblemDetector:
    """Test problem detector initialization and methods."""

    def test_instantiation(self):
        detector = ProblemDetector()
        assert detector is not None

    @pytest.mark.asyncio
    async def test_insert_problem_method(self):
        """Test the _insert_problem static method signature."""
        # Just verify the method exists and is callable
        assert callable(ProblemDetector._insert_problem)


# ═══════════════════════════════════════════════
# Recommendation Engine
# ═══════════════════════════════════════════════

class TestRecommendationEngine:
    """Test recommendation engine utilities."""

    def test_format_headings_none(self):
        engine = RecommendationEngine.__new__(RecommendationEngine)
        assert engine._format_headings(None) == "None"

    def test_format_headings_list(self):
        engine = RecommendationEngine.__new__(RecommendationEngine)
        headings = [
            {"level": "h2", "text": "Introduction"},
            {"level": "h3", "text": "Details"},
        ]
        result = engine._format_headings(headings)
        assert "h2: Introduction" in result
        assert "h3: Details" in result

    def test_format_headings_json_string(self):
        engine = RecommendationEngine.__new__(RecommendationEngine)
        headings_json = json.dumps([{"level": "h2", "text": "Test"}])
        result = engine._format_headings(headings_json)
        assert "h2: Test" in result

    def test_format_headings_empty_list(self):
        engine = RecommendationEngine.__new__(RecommendationEngine)
        assert engine._format_headings([]) == "None"

    def test_parse_json_clean(self):
        engine = RecommendationEngine.__new__(RecommendationEngine)
        result = engine._parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_markdown_block(self):
        engine = RecommendationEngine.__new__(RecommendationEngine)
        result = engine._parse_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_json_with_preamble(self):
        engine = RecommendationEngine.__new__(RecommendationEngine)
        result = engine._parse_json('Here is the result:\n{"key": "value"}\n')
        assert result == {"key": "value"}

    def test_parse_json_invalid(self):
        engine = RecommendationEngine.__new__(RecommendationEngine)
        result = engine._parse_json("not json at all")
        assert "raw_response" in result


# ═══════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════

class TestSchemas:
    """Test new Pydantic model validation."""

    def test_content_problem_response(self):
        from app.models.schemas import ContentProblemResponse
        problem = ContentProblemResponse(
            id=uuid4(),
            post_id=uuid4(),
            problem_type="decay_moderate",
            severity="high",
            details={"drop_percent": 45.2},
            detected_at=datetime.now(timezone.utc),
        )
        assert problem.problem_type == "decay_moderate"
        assert problem.details["drop_percent"] == 45.2

    def test_problem_detection_response(self):
        from app.models.schemas import ProblemDetectionResponse
        resp = ProblemDetectionResponse(decay=3, thin=5, seo=8, orphan=2, total=18)
        assert resp.total == 18

    def test_recommendation_response(self):
        from app.models.schemas import RecommendationResponse
        rec = RecommendationResponse(
            id=uuid4(), post_id=uuid4(),
            recommendation_type="refresh", priority="high",
            estimated_effort_hours=2.5, estimated_impact="high",
            title="Refresh: My Blog Post",
            summary="This post needs updating",
            specific_actions=["Update statistics", "Add new section"],
            ai_generated_content={"target_keywords": ["seo"]},
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert rec.recommendation_type == "refresh"
        assert len(rec.specific_actions) == 2

    def test_recommendation_status_update_valid(self):
        from app.models.schemas import RecommendationStatusUpdate
        update = RecommendationStatusUpdate(status="completed")
        assert update.status == "completed"

    def test_recommendation_status_update_invalid(self):
        from app.models.schemas import RecommendationStatusUpdate
        with pytest.raises(Exception):
            RecommendationStatusUpdate(status="invalid_status")

    def test_recommendation_list_response(self):
        from app.models.schemas import RecommendationListResponse
        resp = RecommendationListResponse(
            recommendations=[],
            total=0,
            by_type={"refresh": 3, "merge": 2},
            by_priority={"high": 2, "medium": 3},
        )
        assert resp.by_type["refresh"] == 3

    def test_content_problem_summary(self):
        from app.models.schemas import ContentProblemSummary
        summary = ContentProblemSummary(
            post_id=uuid4(),
            title="My Post",
            url="https://example.com/post",
            problems=[],
        )
        assert summary.title == "My Post"


# ═══════════════════════════════════════════════
# Migration
# ═══════════════════════════════════════════════

# Migration tests removed — migration files are not in this repo


# ═══════════════════════════════════════════════
# Health Scoring — new factors
# ═══════════════════════════════════════════════

class TestNewHealthFactors:
    """Test the new health scoring factors added in Phase 2."""

    def test_freshness_score_ranges(self):
        from app.services.health_scoring import _freshness_score
        now = datetime.now(timezone.utc)

        assert _freshness_score(now, now) == 100.0
        # Continuous exponential decay: 100 * exp(-0.05 * months_old)
        score_60d = _freshness_score(now - timedelta(days=60), now)
        assert abs(score_60d - 90.6) < 2.0  # ~2 months
        score_120d = _freshness_score(now - timedelta(days=120), now)
        assert abs(score_120d - 82.1) < 2.0  # ~4 months
        score_270d = _freshness_score(now - timedelta(days=270), now)
        assert abs(score_270d - 64.2) < 2.0  # ~9 months
        score_450d = _freshness_score(now - timedelta(days=450), now)
        assert abs(score_450d - 47.7) < 2.0  # ~15 months, above evergreen floor
        score_730d = _freshness_score(now - timedelta(days=730), now)
        assert score_730d == 45.0  # Hits evergreen floor

    def test_content_depth_penalty_short(self):
        from app.services.health_scoring import _content_depth_score
        # 200 words: absolute=8, relative=15, base=11.5
        score_200 = _content_depth_score(200, 1000)
        assert abs(score_200 - 11.5) < 2.0
        # 400 words: absolute=16, relative=15, base=15.5
        score_400 = _content_depth_score(400, 1000)
        assert abs(score_400 - 15.5) < 2.0
        # Short content scores less than long content
        assert score_200 < score_400

    def test_content_depth_bonus_long(self):
        from app.services.health_scoring import _content_depth_score
        score = _content_depth_score(2000, 1000)
        assert score > 85

    def test_technical_seo_perfect(self):
        from app.services.health_scoring import _technical_seo_score
        score = _technical_seo_score(
            meta_description="A well-written meta description with keywords.",
            title="A Perfect Title for SEO Ranking Guide",  # 42 chars
            headings=[{"level": "h2", "text": "Section"}],
            has_outbound=True,
            has_inbound=True,
        )
        # 5 of 8 checks pass (no body_html → no OG, JSON-LD, canonical)
        assert score == 62.5

    def test_technical_seo_nothing(self):
        from app.services.health_scoring import _technical_seo_score
        score = _technical_seo_score(
            meta_description=None, title="Hi",
            headings=None, has_outbound=False, has_inbound=False,
        )
        assert score == 0.0  # "Hi" is 2 chars, below 20 → no partial credit

    def test_engagement_score_bounds(self):
        from app.services.health_scoring import _engagement_score
        # Best possible
        best = _engagement_score(0.0, 300.0)
        assert best >= 95

        # Worst possible
        worst = _engagement_score(1.0, 0.0)
        assert worst == 0.0

    def test_dead_trend_detection(self):
        from app.services.health_scoring import _compute_trend
        trend, score = _compute_trend(1, 1, 2)
        assert trend == "dead"
        assert score == 0.0

    def test_weight_sum_is_one(self):
        from app.services.health_scoring import (
            W_TRAFFIC_TREND, W_RANKING, W_ENGAGEMENT,
            W_FRESHNESS, W_CONTENT_DEPTH, W_INTERNAL_LINKS,
            W_TECHNICAL_SEO, W_AI_READINESS,
        )
        total = (
            W_TRAFFIC_TREND + W_RANKING + W_ENGAGEMENT
            + W_FRESHNESS + W_CONTENT_DEPTH + W_INTERNAL_LINKS
            + W_TECHNICAL_SEO + W_AI_READINESS
        )
        assert abs(total - 1.0) < 0.001
