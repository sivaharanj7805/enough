"""Tests for RAG context retrieval and formatting."""

import pytest
from uuid import UUID
from unittest.mock import AsyncMock, patch, MagicMock
from tests.conftest import TEST_SITE_ID, TEST_POST_ID_A, TEST_POST_ID_B, TEST_CLUSTER_ID, make_record


class TestGetRecommendationContext:
    """Test RAG context retrieval for recommendations."""

    @pytest.mark.asyncio
    async def test_returns_all_context_sections(self):
        """Should return similar_posts, cluster_top_posts, cluster_stats, etc."""
        from app.services.rag_context import get_recommendation_context

        mock_db = AsyncMock()

        # similar posts query
        mock_db.fetch = AsyncMock(side_effect=[
            # _get_similar_posts
            [make_record(
                id=TEST_POST_ID_B, title="Similar Post", url="/similar",
                word_count=2000, health_score=75.0, role="supporter",
                similarity=0.85,
            )],
            # _get_cluster_top_posts
            [make_record(
                id=TEST_POST_ID_B, title="Top Post", url="/top",
                word_count=3000, health_score=90.0, role="pillar",
            )],
            # _get_cannibalization_pairs
            [make_record(
                other_title="Cannibal Post", other_url="/cannibal",
                similarity=0.72, queries=["keyword1", "keyword2"],
            )],
            # _get_inbound_links
            [make_record(
                source_title="Linking Post", source_url="/linker",
                anchor_text="click here",
            )],
        ])

        # _get_cluster_stats
        mock_db.fetchrow = AsyncMock(return_value=make_record(
            id=TEST_CLUSTER_ID, label="Test Cluster", ecosystem_state="forest",
            health_score=70.0, post_count=15, avg_word_count=2000.0,
            avg_health_score=65.0,
        ))

        ctx = await get_recommendation_context(mock_db, TEST_SITE_ID, TEST_POST_ID_A)

        assert len(ctx["similar_posts"]) == 1
        assert ctx["similar_posts"][0]["title"] == "Similar Post"
        assert ctx["similar_posts"][0]["similarity"] == 0.85

        assert len(ctx["cluster_top_posts"]) == 1
        assert ctx["cluster_top_posts"][0]["health_score"] == 90.0

        assert ctx["cluster_stats"]["label"] == "Test Cluster"
        assert ctx["cluster_stats"]["avg_word_count"] == 2000

        assert len(ctx["cannibalization_pairs"]) == 1
        assert ctx["cannibalization_pairs"][0]["queries"] == ["keyword1", "keyword2"]

        assert len(ctx["inbound_links"]) == 1
        assert ctx["inbound_links"][0]["anchor_text"] == "click here"

    @pytest.mark.asyncio
    async def test_handles_empty_results_gracefully(self):
        """Should return empty lists/dicts when no data exists."""
        from app.services.rag_context import get_recommendation_context

        mock_db = AsyncMock()
        mock_db.fetch = AsyncMock(return_value=[])
        mock_db.fetchrow = AsyncMock(return_value=None)

        ctx = await get_recommendation_context(mock_db, TEST_SITE_ID, TEST_POST_ID_A)

        assert ctx["similar_posts"] == []
        assert ctx["cluster_top_posts"] == []
        assert ctx["cluster_stats"] == {}
        assert ctx["cannibalization_pairs"] == []
        assert ctx["inbound_links"] == []


class TestGetBriefContext:
    """Test RAG context retrieval for content briefs."""

    @pytest.mark.asyncio
    async def test_cannibalization_risk_high(self):
        """Should flag high risk when similarity >= 0.80."""
        from app.services.rag_context import get_brief_context

        mock_db = AsyncMock()

        # _find_similar_by_embedding
        mock_db.fetch = AsyncMock(side_effect=[
            [make_record(
                id=TEST_POST_ID_A, title="Existing Post", url="/existing",
                word_count=2000, health_score=65.0, role="supporter",
                similarity=0.85,
            )],
            # _get_cluster_posts_for_brief
            [],
            # _get_link_candidates
            [],
            # _get_keyword_rankings
            [],
        ])

        # _get_nearest_cluster
        mock_db.fetchrow = AsyncMock(side_effect=[
            make_record(
                id=TEST_CLUSTER_ID, label="Test", ecosystem_state="forest",
                health_score=60.0, post_count=10,
            ),
            # _get_cluster_stats_by_id
            make_record(
                label="Test", ecosystem_state="forest", post_count=10,
                avg_word_count=1800.0, avg_health_score=55.0,
            ),
        ])

        ctx = await get_brief_context(mock_db, TEST_SITE_ID, "[0.1,0.2]", "test keyword")

        assert ctx["cannibalization_risk"] == "high"
        assert "WARNING" in ctx["risk_message"]
        assert "Existing Post" in ctx["risk_message"]

    @pytest.mark.asyncio
    async def test_cannibalization_risk_low(self):
        """Should report low risk when no similar posts."""
        from app.services.rag_context import get_brief_context

        mock_db = AsyncMock()
        mock_db.fetch = AsyncMock(side_effect=[
            [make_record(
                id=TEST_POST_ID_A, title="Unrelated", url="/unrelated",
                word_count=1500, health_score=50.0, role="supporter",
                similarity=0.30,
            )],
            [],  # cluster posts
            [],  # link candidates
            [],  # keyword rankings
        ])
        mock_db.fetchrow = AsyncMock(side_effect=[
            None,  # no nearest cluster
        ])

        ctx = await get_brief_context(mock_db, TEST_SITE_ID, "[0.1,0.2]", "new topic")

        assert ctx["cannibalization_risk"] == "low"

    @pytest.mark.asyncio
    async def test_cannibalization_risk_medium(self):
        """Should report medium risk when similarity is 50-80%."""
        from app.services.rag_context import get_brief_context

        mock_db = AsyncMock()
        mock_db.fetch = AsyncMock(side_effect=[
            [make_record(
                id=TEST_POST_ID_A, title="Related Post", url="/related",
                word_count=1500, health_score=50.0, role="supporter",
                similarity=0.65,
            )],
            [],  # cluster posts
            [],  # link candidates
            [],  # keyword rankings
        ])
        mock_db.fetchrow = AsyncMock(side_effect=[
            None,  # no nearest cluster
        ])

        ctx = await get_brief_context(mock_db, TEST_SITE_ID, "[0.1,0.2]", "topic")

        assert ctx["cannibalization_risk"] == "medium"
        assert "differentiate" in ctx["risk_message"].lower()


class TestFormatRecommendationContext:
    """Test formatting of RAG context into prompt text."""

    def test_formats_all_sections(self):
        from app.services.rag_context import format_recommendation_context

        ctx = {
            "similar_posts": [
                {"title": "Post A", "url": "/a", "word_count": 2000,
                 "health_score": 80.0, "role": "pillar", "similarity": 0.9},
            ],
            "cluster_top_posts": [
                {"title": "Top Post", "url": "/top", "word_count": 3000,
                 "health_score": 95.0, "role": "pillar"},
            ],
            "cluster_stats": {
                "label": "Email Marketing",
                "ecosystem_state": "forest",
                "avg_word_count": 2400,
                "avg_health_score": 72.0,
                "post_count": 12,
            },
            "cannibalization_pairs": [
                {"other_title": "Competitor", "other_url": "/comp",
                 "similarity": 0.73, "queries": ["email", "marketing"]},
            ],
            "inbound_links": [
                {"source_title": "Linker", "source_url": "/link",
                 "anchor_text": "email tips"},
            ],
        }

        text = format_recommendation_context(ctx)

        assert "SIMILAR POSTS" in text
        assert "Post A" in text
        assert "TOP PERFORMERS" in text
        assert "CLUSTER BENCHMARKS" in text
        assert "Email Marketing" in text
        assert "2400" in text
        assert "CANNIBALIZATION PAIRS" in text
        assert "POSTS LINKING TO THIS POST" in text
        assert "email tips" in text

    def test_handles_empty_context(self):
        from app.services.rag_context import format_recommendation_context

        ctx = {
            "similar_posts": [],
            "cluster_top_posts": [],
            "cluster_stats": {},
            "cannibalization_pairs": [],
            "inbound_links": [],
        }

        text = format_recommendation_context(ctx)
        assert text == "(No additional context available)"


class TestFormatBriefContext:
    """Test formatting of RAG context for brief generation."""

    def test_formats_risk_and_cluster(self):
        from app.services.rag_context import format_brief_context

        ctx = {
            "cannibalization_risk": "medium",
            "risk_message": "Related posts exist (65% similar).",
            "similar_existing": [
                {"title": "Email Guide", "url": "/email", "word_count": 2000,
                 "health_score": 70.0, "similarity": 0.65},
            ],
            "nearest_cluster": {
                "label": "Email Marketing", "ecosystem_state": "forest",
                "health_score": 70.0, "post_count": 10,
            },
            "cluster_stats": {
                "avg_word_count": 2200, "avg_health_score": 68.0,
                "post_count": 10,
            },
            "cluster_posts": [],
            "link_candidates": [
                {"title": "Link Post", "url": "/link", "direction": "to",
                 "word_count": 1500, "health_score": 60.0, "similarity": 0.5},
            ],
            "existing_rankings": [],
        }

        text = format_brief_context(ctx)

        assert "CANNIBALIZATION RISK: MEDIUM" in text
        assert "Email Guide" in text
        assert "Email Marketing" in text
        assert "2200" in text
        assert "POSTS THIS NEW POST SHOULD LINK TO" in text
