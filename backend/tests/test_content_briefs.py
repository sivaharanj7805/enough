"""Tests for RAG-powered content brief generation."""

import json
import pytest
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock

from tests.conftest import TEST_SITE_ID, TEST_POST_ID_A, TEST_CLUSTER_ID, make_record


class TestContentBriefGenerator:
    """Test the ContentBriefGenerator service."""

    @pytest.mark.asyncio
    async def test_generate_brief_full_flow(self):
        """Should embed topic, retrieve context, call Claude, and store result."""
        from app.services.content_briefs import ContentBriefGenerator

        mock_db = AsyncMock()
        brief_uuid = uuid4()

        # Mock DB calls in order:
        # 1. get_brief_context calls (similar, cluster, links, rankings)
        mock_db.fetch = AsyncMock(side_effect=[
            # _find_similar_by_embedding
            [make_record(
                id=TEST_POST_ID_A, title="Existing API Post", url="/api-guide",
                word_count=2000, health_score=65.0, role="supporter",
                similarity=0.45,
            )],
            # _get_cluster_posts_for_brief
            [make_record(
                id=TEST_POST_ID_A, title="API Auth", url="/api-auth",
                word_count=2500, health_score=80.0, role="pillar",
            )],
            # _get_link_candidates
            [make_record(
                id=TEST_POST_ID_A, title="API Basics", url="/api-basics",
                word_count=1800, health_score=70.0, role="supporter",
                internal_pagerank=0.3, similarity=0.6,
            )],
            # _get_keyword_rankings
            [],
            # _get_secondary_keywords
            [make_record(query="api rate limiting best practices", total_imp=500)],
        ])

        mock_db.fetchrow = AsyncMock(side_effect=[
            # _get_nearest_cluster
            make_record(
                id=TEST_CLUSTER_ID, label="API Development",
                ecosystem_state="forest", health_score=72.0, post_count=8,
            ),
            # _get_cluster_stats_by_id
            make_record(
                label="API Development", ecosystem_state="forest",
                post_count=8, avg_word_count=2100.0, avg_health_score=68.0,
            ),
        ])

        # Mock fetchval for the INSERT RETURNING id
        mock_db.fetchval = AsyncMock(return_value=brief_uuid)

        # Mock OpenAI embedding
        mock_openai_resp = MagicMock()
        mock_openai_resp.data = [MagicMock(embedding=[0.1] * 1536)]

        # Mock Claude response
        brief_json = {
            "suggested_titles": ["API Rate Limiting Guide", "Master Rate Limiting"],
            "secondary_keywords": ["rate limit", "throttling", "429"],
            "recommended_word_count": 2200,
            "outline": [
                {"level": "h2", "text": "What Is Rate Limiting", "bullets": ["Definition"], "estimated_words": 300},
                {"level": "h2", "text": "Implementation", "bullets": ["Code examples"], "estimated_words": 800},
            ],
            "questions_to_answer": ["How to implement rate limiting?"],
            "avoid_topics": ["API authentication basics"],
            "content_angle": "Production implementation focus",
            "difficulty_level": "intermediate",
            "opening_hook": "Start with a real-world outage story",
            "cta_suggestion": "Link to API monitoring tool",
            "internal_links_suggested": [],
            "content_type": "guide",
            "confidence": 0.85,
        }

        mock_claude_resp = MagicMock()
        mock_claude_resp.content = [MagicMock(text=json.dumps(brief_json))]

        with patch.object(ContentBriefGenerator, '__init__', lambda self: None):
            generator = ContentBriefGenerator()
            generator.openai = AsyncMock()
            generator.openai.embeddings.create = AsyncMock(return_value=mock_openai_resp)
            generator.anthropic = AsyncMock()
            generator.anthropic.messages.create = AsyncMock(return_value=mock_claude_resp)
            generator.rate_limiter = AsyncMock()
            generator.rate_limiter.wait = AsyncMock()

            result = await generator.generate_brief(mock_db, TEST_SITE_ID, "API rate limiting")

        assert "error" not in result
        assert result["brief_id"] == str(brief_uuid)
        assert result["target_keyword"] == "API rate limiting"
        assert result["cannibalization_risk"] == "low"
        assert len(result["suggested_titles"]) == 2
        assert result["recommended_word_count"] == 2200
        assert result["content_angle"] == "Production implementation focus"
        assert "API authentication basics" in result["avoid_topics"]

    @pytest.mark.asyncio
    async def test_generate_brief_high_cannibalization_risk(self):
        """Should flag high risk and include warning in result."""
        from app.services.content_briefs import ContentBriefGenerator

        mock_db = AsyncMock()
        brief_uuid = uuid4()

        mock_db.fetch = AsyncMock(side_effect=[
            # _find_similar_by_embedding — very similar post
            [make_record(
                id=TEST_POST_ID_A, title="API Rate Limiting Guide", url="/api-rate-limiting",
                word_count=2500, health_score=75.0, role="pillar",
                similarity=0.88,
            )],
            # _get_cluster_posts_for_brief
            [],
            # _get_link_candidates
            [],
            # _get_keyword_rankings
            [],
            # _get_secondary_keywords
            [],
        ])

        mock_db.fetchrow = AsyncMock(side_effect=[
            make_record(
                id=TEST_CLUSTER_ID, label="APIs", ecosystem_state="swamp",
                health_score=45.0, post_count=15,
            ),
            make_record(
                label="APIs", ecosystem_state="swamp", post_count=15,
                avg_word_count=1800.0, avg_health_score=50.0,
            ),
        ])
        mock_db.fetchval = AsyncMock(return_value=brief_uuid)

        mock_openai_resp = MagicMock()
        mock_openai_resp.data = [MagicMock(embedding=[0.1] * 1536)]

        brief_json = {
            "suggested_titles": ["Advanced Rate Limiting"],
            "secondary_keywords": [],
            "recommended_word_count": 2000,
            "outline": [],
            "questions_to_answer": [],
            "avoid_topics": ["Basic rate limiting concepts"],
            "content_angle": "Advanced patterns",
            "difficulty_level": "advanced",
            "content_type": "guide",
            "confidence": 0.6,
        }
        mock_claude_resp = MagicMock()
        mock_claude_resp.content = [MagicMock(text=json.dumps(brief_json))]

        with patch.object(ContentBriefGenerator, '__init__', lambda self: None):
            generator = ContentBriefGenerator()
            generator.openai = AsyncMock()
            generator.openai.embeddings.create = AsyncMock(return_value=mock_openai_resp)
            generator.anthropic = AsyncMock()
            generator.anthropic.messages.create = AsyncMock(return_value=mock_claude_resp)
            generator.rate_limiter = AsyncMock()
            generator.rate_limiter.wait = AsyncMock()

            result = await generator.generate_brief(mock_db, TEST_SITE_ID, "API rate limiting")

        assert result["cannibalization_risk"] == "high"
        assert "WARNING" in result["risk_message"]
        assert "API Rate Limiting Guide" in result["risk_message"]

    @pytest.mark.asyncio
    async def test_generate_brief_embedding_failure(self):
        """Should return error when embedding generation fails."""
        from app.services.content_briefs import ContentBriefGenerator

        mock_db = AsyncMock()

        with patch.object(ContentBriefGenerator, '__init__', lambda self: None):
            generator = ContentBriefGenerator()
            generator.openai = AsyncMock()
            generator.openai.embeddings.create = AsyncMock(
                side_effect=Exception("API error")
            )

            result = await generator.generate_brief(mock_db, TEST_SITE_ID, "test topic")

        assert result == {"error": "Failed to generate topic embedding"}

    @pytest.mark.asyncio
    async def test_parse_json_response_with_markdown(self):
        """Should handle markdown-wrapped JSON responses."""
        from app.services.content_briefs import ContentBriefGenerator

        raw = '```json\n{"key": "value"}\n```'
        result = ContentBriefGenerator._parse_json_response(raw)
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_parse_json_response_plain(self):
        """Should handle plain JSON responses."""
        from app.services.content_briefs import ContentBriefGenerator

        raw = '{"key": "value"}'
        result = ContentBriefGenerator._parse_json_response(raw)
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_parse_json_response_with_preamble(self):
        """Should extract JSON from text with preamble."""
        from app.services.content_briefs import ContentBriefGenerator

        raw = 'Here is the brief:\n{"key": "value"}\n\nHope this helps!'
        result = ContentBriefGenerator._parse_json_response(raw)
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_parse_json_response_invalid(self):
        """Should return None for unparseable responses."""
        from app.services.content_briefs import ContentBriefGenerator

        raw = 'This is not JSON at all'
        result = ContentBriefGenerator._parse_json_response(raw)
        assert result is None


class TestContentBriefEndpoints:
    """Test the content brief API endpoints exist and validate input."""

    @pytest.mark.asyncio
    async def test_brief_request_requires_topic(self):
        """ContentBriefRequest should require a topic field."""
        from app.routers.intelligence import ContentBriefRequest

        brief = ContentBriefRequest(topic="API rate limiting")
        assert brief.topic == "API rate limiting"

    @pytest.mark.asyncio
    async def test_brief_request_model_fields(self):
        """ContentBriefRequest should have the right fields."""
        from app.routers.intelligence import ContentBriefRequest

        fields = ContentBriefRequest.model_fields
        assert "topic" in fields
