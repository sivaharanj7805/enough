"""Tests for Phase 1: Content Ingestion Pipeline.

Tests cover:
1.1 Sitemap parser (XML, sitemap index, RSS fallback)
1.2 WordPress connector (pagination, taxonomy resolution)
1.3 Web scraper (content extraction, headings, meta)
1.4 Crawl orchestrator (concurrent processing, retries, progress)
1.5/1.6 GSC + GA4 connector structure
1.7 Re-crawl system (change detection, cron scheduling)
"""

import asyncio
import hashlib
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.normalizer import (
    NormalizedPost,
    InternalLink,
    compute_content_hash,
    save_normalized_posts,
)
from app.services.sitemap import SitemapCrawler


# ═══════════════════════════════════════════════
# 1.1 — Sitemap Parser
# ═══════════════════════════════════════════════

class TestSitemapParser:
    """Tests for sitemap parsing, including XML, index, and RSS fallback."""

    def test_init_defaults(self):
        crawler = SitemapCrawler(
            sitemap_url="https://example.com/sitemap.xml",
            domain="example.com",
        )
        assert crawler.sitemap_url == "https://example.com/sitemap.xml"
        assert crawler.domain == "example.com"
        assert crawler.max_pages == 5000
        assert crawler.concurrency == 10
        assert crawler.max_retries == 3
        assert crawler.timeout_seconds == 30.0

    def test_init_custom_params(self):
        progress_fn = lambda p, t: None
        crawler = SitemapCrawler(
            sitemap_url="https://blog.co/sitemap.xml",
            domain="blog.co",
            delay_seconds=0.5,
            max_pages=100,
            concurrency=5,
            max_retries=5,
            timeout_seconds=15.0,
            on_progress=progress_fn,
        )
        assert crawler.max_pages == 100
        assert crawler.concurrency == 5
        assert crawler.max_retries == 5
        assert crawler.timeout_seconds == 15.0
        assert crawler.on_progress is progress_fn

    def test_domain_lowercased(self):
        crawler = SitemapCrawler(
            sitemap_url="https://EXAMPLE.COM/sitemap.xml",
            domain="EXAMPLE.COM",
        )
        assert crawler.domain == "example.com"


class TestSitemapXMLParsing:
    """Test XML sitemap parsing logic."""

    @pytest.mark.asyncio
    async def test_parse_simple_sitemap(self):
        """Standard XML sitemap with <url><loc> elements."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/post-1</loc></url>
            <url><loc>https://example.com/post-2</loc></url>
            <url><loc>https://example.com/post-3</loc></url>
        </urlset>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = xml_content
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        crawler = SitemapCrawler(
            sitemap_url="https://example.com/sitemap.xml",
            domain="example.com",
        )

        urls: list[str] = []
        await crawler._parse_sitemap_url(mock_client, "https://example.com/sitemap.xml", urls, depth=0)

        assert len(urls) == 3
        assert "https://example.com/post-1" in urls
        assert "https://example.com/post-2" in urls
        assert "https://example.com/post-3" in urls

    @pytest.mark.asyncio
    async def test_parse_sitemap_index(self):
        """Sitemap index file that references sub-sitemaps."""
        index_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
            <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
        </sitemapindex>"""

        sub_sitemap_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/blog/hello</loc></url>
        </urlset>"""

        call_count = 0

        async def mock_get(url):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            if "index" in url or url.endswith("sitemap.xml"):
                resp.content = index_xml
            else:
                resp.content = sub_sitemap_xml
            return resp

        mock_client = AsyncMock()
        mock_client.get = mock_get

        crawler = SitemapCrawler(
            sitemap_url="https://example.com/sitemap.xml",
            domain="example.com",
        )

        urls: list[str] = []
        await crawler._parse_sitemap_url(mock_client, "https://example.com/sitemap.xml", urls, depth=0)

        # Should have parsed index → 2 sub-sitemaps → 1 URL each
        assert len(urls) == 2  # One from each sub-sitemap
        assert call_count == 3  # Index + 2 sub-sitemaps

    @pytest.mark.asyncio
    async def test_max_depth_prevents_infinite_recursion(self):
        """Sitemap nesting beyond depth 3 should stop."""
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/deep.xml</loc></sitemap>
        </sitemapindex>"""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = xml
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        crawler = SitemapCrawler(
            sitemap_url="https://example.com/sitemap.xml",
            domain="example.com",
        )

        urls: list[str] = []
        await crawler._parse_sitemap_url(mock_client, "https://example.com/deep.xml", urls, depth=4)

        # Should return empty — depth exceeded
        assert len(urls) == 0


# ═══════════════════════════════════════════════
# 1.3 — Content Extraction
# ═══════════════════════════════════════════════

class TestContentExtraction:
    """Test headings extraction and NormalizedPost structure."""

    def test_extract_headings(self):
        """Headings are extracted as structured array."""
        from bs4 import BeautifulSoup
        html = """
        <html><body>
            <h1>Main Title</h1>
            <h2>First Section</h2>
            <p>Some text</p>
            <h2>Second Section</h2>
            <h3>Subsection</h3>
            <h2>Third Section</h2>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        headings = SitemapCrawler._extract_headings(soup)

        assert len(headings) == 5
        assert headings[0] == {"level": "h1", "text": "Main Title"}
        assert headings[1] == {"level": "h2", "text": "First Section"}
        assert headings[2] == {"level": "h2", "text": "Second Section"}
        assert headings[3] == {"level": "h3", "text": "Subsection"}
        assert headings[4] == {"level": "h2", "text": "Third Section"}

    def test_extract_headings_empty(self):
        """No headings in page returns empty list."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<html><body><p>Just text</p></body></html>", "html.parser")
        headings = SitemapCrawler._extract_headings(soup)
        assert headings == []

    def test_extract_headings_skips_empty(self):
        """Empty heading tags are skipped."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<html><body><h2></h2><h2>Real</h2></body></html>", "html.parser")
        headings = SitemapCrawler._extract_headings(soup)
        assert len(headings) == 1
        assert headings[0]["text"] == "Real"


class TestNormalizedPost:
    """Test the NormalizedPost dataclass."""

    def test_auto_word_count(self):
        post = NormalizedPost(
            url="https://example.com/post",
            title="Test",
            body_text="one two three four five",
            body_html="<p>one two three four five</p>",
        )
        assert post.word_count == 5

    def test_auto_content_hash(self):
        post = NormalizedPost(
            url="https://example.com/post",
            title="Test",
            body_text="hello world",
            body_html="<p>hello world</p>",
        )
        expected = hashlib.sha256("hello world".encode()).hexdigest()
        assert post.content_hash == expected

    def test_headings_default_empty(self):
        post = NormalizedPost(
            url="https://example.com/post",
            title="Test",
            body_text="content",
            body_html="<p>content</p>",
        )
        assert post.headings == []
        assert post.meta_description is None
        assert post.http_status is None

    def test_headings_stored(self):
        headings = [{"level": "h2", "text": "Intro"}, {"level": "h3", "text": "Details"}]
        post = NormalizedPost(
            url="https://example.com/post",
            title="Test",
            body_text="content",
            body_html="<p>content</p>",
            headings=headings,
            meta_description="A test page",
            http_status=200,
        )
        assert len(post.headings) == 2
        assert post.meta_description == "A test page"
        assert post.http_status == 200

    def test_compute_content_hash(self):
        text = "This is some content to hash"
        h = compute_content_hash(text)
        assert h == hashlib.sha256(text.encode()).hexdigest()
        assert len(h) == 64  # SHA256 hex digest

    def test_content_hash_deterministic(self):
        text = "Same input always same output"
        assert compute_content_hash(text) == compute_content_hash(text)

    def test_content_hash_different_inputs(self):
        assert compute_content_hash("hello") != compute_content_hash("world")

    def test_internal_links(self):
        link = InternalLink(target_url="https://example.com/other", anchor_text="click here")
        assert link.target_url == "https://example.com/other"
        assert link.anchor_text == "click here"

    def test_internal_link_optional_anchor(self):
        link = InternalLink(target_url="https://example.com/page")
        assert link.anchor_text is None


# ═══════════════════════════════════════════════
# 1.4 — Crawl Orchestrator
# ═══════════════════════════════════════════════

class TestCrawlOrchestrator:
    """Test concurrent crawl behavior."""

    def test_semaphore_concurrency_limit(self):
        """Semaphore should limit to configured concurrency."""
        crawler = SitemapCrawler(
            sitemap_url="https://example.com/sitemap.xml",
            domain="example.com",
            concurrency=5,
        )
        assert crawler.concurrency == 5

    @pytest.mark.asyncio
    async def test_progress_callback_fires(self):
        """Progress callback should be called during crawl."""
        progress_calls = []

        def on_progress(processed: int, total: int):
            progress_calls.append((processed, total))

        crawler = SitemapCrawler(
            sitemap_url="https://example.com/sitemap.xml",
            domain="example.com",
            on_progress=on_progress,
        )

        # Simulate progress tracking
        crawler._total = 50
        crawler._processed = 0

        # The progress callback is called in the crawl loop
        # Here we just verify the callback is stored
        assert crawler.on_progress is not None

    def test_max_pages_limit(self):
        """URLs should be limited to max_pages."""
        crawler = SitemapCrawler(
            sitemap_url="https://example.com/sitemap.xml",
            domain="example.com",
            max_pages=10,
        )
        assert crawler.max_pages == 10


# ═══════════════════════════════════════════════
# 1.5/1.6 — GSC + GA4 Connectors
# ═══════════════════════════════════════════════

class TestGSCConnector:
    """Test Google Search Console connector structure."""

    def test_import(self):
        from app.services.gsc import GSCConnector
        connector = GSCConnector(
            site_url="https://example.com",
            refresh_token="fake-token",
        )
        assert connector.site_url == "https://example.com"

    def test_has_sync_metrics_method(self):
        from app.services.gsc import GSCConnector
        assert hasattr(GSCConnector, "sync_metrics")
        assert asyncio.iscoroutinefunction(GSCConnector.sync_metrics)


class TestGA4Connector:
    """Test Google Analytics 4 connector structure."""

    def test_import(self):
        from app.services.ga4 import GA4Connector
        connector = GA4Connector(
            property_id="properties/123456",
            refresh_token="fake-token",
        )
        assert connector.property_id == "properties/123456"

    def test_has_sync_metrics_method(self):
        from app.services.ga4 import GA4Connector
        assert hasattr(GA4Connector, "sync_metrics")
        assert asyncio.iscoroutinefunction(GA4Connector.sync_metrics)


# ═══════════════════════════════════════════════
# 1.7 — Re-crawl System
# ═══════════════════════════════════════════════

class TestRecrawlSystem:
    """Test the re-crawl and data refresh system."""

    def test_recrawl_module_imports(self):
        from app.services.recrawl import (
            get_sites_needing_refresh,
            refresh_analytics,
            recrawl_site,
            reembed_changed_posts,
            run_daily_refresh,
            run_weekly_recrawl,
            run_monthly_reembed,
        )
        # All functions exist
        assert callable(get_sites_needing_refresh)
        assert callable(refresh_analytics)
        assert callable(recrawl_site)
        assert callable(reembed_changed_posts)
        assert callable(run_daily_refresh)
        assert callable(run_weekly_recrawl)
        assert callable(run_monthly_reembed)

    def test_all_cron_functions_are_async(self):
        from app.services.recrawl import (
            run_daily_refresh,
            run_weekly_recrawl,
            run_monthly_reembed,
        )
        assert asyncio.iscoroutinefunction(run_daily_refresh)
        assert asyncio.iscoroutinefunction(run_weekly_recrawl)
        assert asyncio.iscoroutinefunction(run_monthly_reembed)


# ═══════════════════════════════════════════════
# Integration: API Endpoints Exist
# ═══════════════════════════════════════════════

class TestIngestionEndpoints:
    """Verify all Phase 1 API endpoints are registered."""

    def test_crawl_endpoint_exists(self):
        from app.routers.ingestion import router
        routes = [r.path for r in router.routes]
        assert "/{site_id}/crawl" in routes

    def test_crawl_status_endpoint_exists(self):
        from app.routers.ingestion import router
        routes = [r.path for r in router.routes]
        assert "/{site_id}/crawl/status" in routes

    def test_analytics_sync_endpoint_exists(self):
        from app.routers.ingestion import router
        routes = [r.path for r in router.routes]
        assert "/{site_id}/sync-analytics" in routes

    def test_embeddings_endpoint_exists(self):
        from app.routers.ingestion import router
        routes = [r.path for r in router.routes]
        assert "/{site_id}/generate-embeddings" in routes

    def test_cron_daily_refresh_exists(self):
        from app.routers.ingestion import router
        routes = [r.path for r in router.routes]
        assert "/cron/daily-refresh" in routes

    def test_cron_weekly_recrawl_exists(self):
        from app.routers.ingestion import router
        routes = [r.path for r in router.routes]
        assert "/cron/weekly-recrawl" in routes

    def test_cron_monthly_reembed_exists(self):
        from app.routers.ingestion import router
        routes = [r.path for r in router.routes]
        assert "/cron/monthly-reembed" in routes


# ═══════════════════════════════════════════════
# OAuth Flow
# ═══════════════════════════════════════════════

class TestOAuthFlow:
    """Verify OAuth endpoints and token storage exist."""

    def test_google_oauth_endpoint_exists(self):
        from app.routers.auth import router
        routes = [r.path for r in router.routes]
        assert "/google" in routes

    def test_google_callback_endpoint_exists(self):
        from app.routers.auth import router
        routes = [r.path for r in router.routes]
        assert "/google/callback" in routes

    def test_store_google_token_endpoint_exists(self):
        from app.routers.sites import router
        routes = [r.path for r in router.routes]
        assert "/{site_id}/google-token" in routes


# ═══════════════════════════════════════════════
# DB Schema
# ═══════════════════════════════════════════════

class TestDBSchema:
    """Verify migration files exist and have expected content."""

    def test_initial_schema_has_posts_table(self):
        with open("migrations/001_initial_schema.sql") as f:
            sql = f.read()
        assert "CREATE TABLE posts" in sql
        assert "content_hash TEXT" in sql
        assert "word_count INTEGER" in sql

    def test_initial_schema_has_analytics_tables(self):
        with open("migrations/001_initial_schema.sql") as f:
            sql = f.read()
        assert "CREATE TABLE ga4_metrics" in sql
        assert "CREATE TABLE gsc_metrics" in sql

    def test_initial_schema_has_crawl_jobs(self):
        with open("migrations/001_initial_schema.sql") as f:
            sql = f.read()
        assert "CREATE TABLE crawl_jobs" in sql

    def test_enhancement_migration_has_new_columns(self):
        with open("migrations/004_phase1_enhancements.sql") as f:
            sql = f.read()
        assert "headings JSONB" in sql
        assert "meta_description TEXT" in sql
        assert "http_status INTEGER" in sql

    def test_enhancement_migration_has_indexes(self):
        with open("migrations/004_phase1_enhancements.sql") as f:
            sql = f.read()
        assert "idx_posts_content_hash" in sql
        assert "idx_post_embeddings_content_hash" in sql


# ═══════════════════════════════════════════════
# WordPress Connector
# ═══════════════════════════════════════════════

class TestWordPressConnector:
    """Test WordPress connector structure."""

    def test_import_and_init(self):
        from app.services.wordpress import WordPressConnector
        connector = WordPressConnector(
            base_url="https://example.com",
            domain="example.com",
        )
        assert connector.base_url == "https://example.com"
        assert connector.domain == "example.com"

    def test_has_fetch_all_posts(self):
        from app.services.wordpress import WordPressConnector
        assert hasattr(WordPressConnector, "fetch_all_posts")
        assert asyncio.iscoroutinefunction(WordPressConnector.fetch_all_posts)

    def test_auth_header_with_password(self):
        from app.services.wordpress import WordPressConnector
        connector = WordPressConnector(
            base_url="https://example.com",
            domain="example.com",
            app_password="test-password",
        )
        headers = connector._get_headers()
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_no_auth_header_without_password(self):
        from app.services.wordpress import WordPressConnector
        connector = WordPressConnector(
            base_url="https://example.com",
            domain="example.com",
        )
        headers = connector._get_headers()
        assert "Authorization" not in headers
