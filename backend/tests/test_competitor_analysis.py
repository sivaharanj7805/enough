"""Tests for competitor analysis service."""

import pytest
from uuid import uuid4


class TestCompetitorAnalyzerImport:
    """Verify competitor analyzer imports cleanly."""

    def test_import(self):
        from app.services.competitor_analysis import CompetitorAnalyzer
        assert CompetitorAnalyzer is not None

    def test_constants(self):
        from app.services.competitor_analysis import (
            MAX_COMPETITOR_POSTS,
            SIMILARITY_THRESHOLD,
        )
        assert MAX_COMPETITOR_POSTS == 200
        assert SIMILARITY_THRESHOLD == 0.35

    def test_has_required_methods(self):
        from app.services.competitor_analysis import CompetitorAnalyzer
        analyzer = CompetitorAnalyzer()
        assert hasattr(analyzer, 'add_competitor')
        assert hasattr(analyzer, 'crawl_competitor')
        assert hasattr(analyzer, 'embed_competitor_content')
        assert hasattr(analyzer, 'analyze_competition')
        assert hasattr(analyzer, 'get_coverage_comparison')


class TestDomainNormalization:
    """Test domain normalization in add_competitor."""

    @pytest.mark.asyncio
    async def test_strips_protocol(self):
        """Domain should be normalized from full URL."""
        from unittest.mock import AsyncMock, MagicMock
        from app.services.competitor_analysis import CompetitorAnalyzer

        analyzer = CompetitorAnalyzer()
        db = MagicMock()
        db.fetchval = AsyncMock(return_value=uuid4())

        await analyzer.add_competitor(db, uuid4(), "https://www.example.com/blog")

        # Verify the domain was normalized
        call_args = db.fetchval.call_args
        domain_arg = call_args[0][2]  # 3rd positional arg is domain
        assert domain_arg == "example.com"

    @pytest.mark.asyncio
    async def test_strips_www(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.competitor_analysis import CompetitorAnalyzer

        analyzer = CompetitorAnalyzer()
        db = MagicMock()
        db.fetchval = AsyncMock(return_value=uuid4())

        await analyzer.add_competitor(db, uuid4(), "www.competitor.io")

        call_args = db.fetchval.call_args
        domain_arg = call_args[0][2]
        assert domain_arg == "competitor.io"

    @pytest.mark.asyncio
    async def test_lowercases(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.services.competitor_analysis import CompetitorAnalyzer

        analyzer = CompetitorAnalyzer()
        db = MagicMock()
        db.fetchval = AsyncMock(return_value=uuid4())

        await analyzer.add_competitor(db, uuid4(), "EXAMPLE.COM")

        call_args = db.fetchval.call_args
        domain_arg = call_args[0][2]
        assert domain_arg == "example.com"
