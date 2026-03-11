"""Universal sitemap crawler.

Parses XML sitemaps (including sitemap index files), fetches each URL,
extracts content using trafilatura, and normalizes to the standard schema.
"""

import logging
from urllib.parse import urlparse, urljoin
from xml.etree import ElementTree

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.services.normalizer import NormalizedPost, InternalLink, compute_content_hash
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# XML namespace for sitemaps
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class SitemapCrawler:
    """Crawl a website via its XML sitemap and extract content."""

    def __init__(
        self,
        sitemap_url: str,
        domain: str,
        delay_seconds: float = 1.0,
        max_pages: int = 5000,
    ):
        self.sitemap_url = sitemap_url
        self.domain = domain.lower()
        self.rate_limiter = RateLimiter(requests_per_second=1.0 / delay_seconds)
        self.max_pages = max_pages

    async def crawl(self) -> list[NormalizedPost]:
        """Crawl all URLs from the sitemap and extract content."""
        urls = await self._parse_sitemap()
        logger.info("Sitemap: found %d URLs for %s", len(urls), self.domain)

        # Limit to max_pages
        if len(urls) > self.max_pages:
            logger.warning(
                "Sitemap has %d URLs, limiting to %d", len(urls), self.max_pages,
            )
            urls = urls[: self.max_pages]

        posts: list[NormalizedPost] = []
        async with httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": "Enough/0.1 (Content Intelligence Bot)"},
            follow_redirects=True,
        ) as client:
            for i, url in enumerate(urls):
                await self.rate_limiter.wait()
                try:
                    post = await self._fetch_and_extract(client, url)
                    if post:
                        posts.append(post)
                except Exception as e:
                    logger.warning("Failed to process %s: %s", url, e)
                    continue

                if (i + 1) % 50 == 0:
                    logger.info("Sitemap: processed %d/%d URLs", i + 1, len(urls))

        logger.info("Sitemap: extracted %d posts from %d URLs", len(posts), len(urls))
        return posts

    async def _parse_sitemap(self) -> list[str]:
        """Parse the sitemap XML, handling sitemap index files recursively."""
        urls: list[str] = []

        async with httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": "Enough/0.1"},
            follow_redirects=True,
        ) as client:
            await self._parse_sitemap_url(client, self.sitemap_url, urls, depth=0)

        return urls

    async def _parse_sitemap_url(
        self,
        client: httpx.AsyncClient,
        url: str,
        urls: list[str],
        depth: int,
    ) -> None:
        """Recursively parse a sitemap URL."""
        if depth > 3:
            logger.warning("Sitemap nesting too deep at %s, stopping", url)
            return

        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch sitemap %s: %s", url, e)
            return

        try:
            root = ElementTree.fromstring(resp.content)
        except ElementTree.ParseError as e:
            logger.error("Failed to parse sitemap XML %s: %s", url, e)
            return

        # Check if this is a sitemap index
        sitemaps = root.findall("sm:sitemap/sm:loc", SITEMAP_NS)
        if sitemaps:
            logger.info("Sitemap index found at %s with %d sub-sitemaps", url, len(sitemaps))
            for sm_loc in sitemaps:
                if sm_loc.text:
                    await self._parse_sitemap_url(client, sm_loc.text.strip(), urls, depth + 1)
            return

        # Regular sitemap — extract URLs
        for loc in root.findall("sm:url/sm:loc", SITEMAP_NS):
            if loc.text:
                urls.append(loc.text.strip())

    async def _fetch_and_extract(
        self, client: httpx.AsyncClient, url: str
    ) -> NormalizedPost | None:
        """Fetch a page and extract content using trafilatura."""
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Failed to fetch %s: %s", url, e)
            return None

        html = resp.text

        # Use trafilatura for main content extraction
        body_text = trafilatura.extract(html) or ""
        if not body_text or len(body_text.strip()) < 50:
            # Too short — probably not a content page
            return None

        # Extract title
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else url

        # Extract HTML of main content area
        body_html = trafilatura.extract(html, output_format="xml") or html

        # Extract internal links from full page HTML
        internal_links = self._extract_internal_links(soup, url)

        # Extract slug from URL
        parsed = urlparse(url)
        slug = parsed.path.strip("/").split("/")[-1] if parsed.path.strip("/") else None

        # Attempt to find publish date via trafilatura metadata
        metadata = trafilatura.extract_metadata(html)
        publish_date = None
        if metadata and metadata.date:
            from datetime import datetime, timezone
            try:
                publish_date = datetime.fromisoformat(str(metadata.date)).replace(
                    tzinfo=timezone.utc
                )
            except (ValueError, TypeError):
                pass

        return NormalizedPost(
            url=url,
            slug=slug,
            title=title,
            body_text=body_text,
            body_html=body_html,
            publish_date=publish_date,
            internal_links=internal_links,
            cms_categories=[],
            cms_tags=[],
            word_count=len(body_text.split()),
            content_hash=compute_content_hash(body_text),
        )

    def _extract_internal_links(self, soup: BeautifulSoup, current_url: str) -> list[InternalLink]:
        """Extract links to the same domain."""
        links: list[InternalLink] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            parsed = urlparse(href)

            # Resolve relative URLs
            if not parsed.netloc:
                href = urljoin(current_url, href)
                parsed = urlparse(href)

            if parsed.netloc.lower().replace("www.", "") == self.domain.replace("www.", ""):
                anchor_text = anchor.get_text(strip=True)
                links.append(InternalLink(target_url=href, anchor_text=anchor_text or None))

        return links
