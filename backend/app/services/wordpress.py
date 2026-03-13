"""WordPress REST API connector.

Fetches all published posts from a WordPress site, resolves categories/tags,
extracts internal links, and normalizes to the standard schema.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.normalizer import NormalizedPost, InternalLink, compute_content_hash
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class WordPressConnector:
    """Fetch and normalize posts from a WordPress REST API."""

    def __init__(
        self,
        base_url: str,
        domain: str,
        app_password: str | None = None,
        per_page: int = 100,
    ):
        self.base_url = base_url.rstrip("/")
        self.domain = domain.lower()
        self.app_password = app_password
        self.per_page = per_page
        self.rate_limiter = RateLimiter(requests_per_second=5)

        # Caches for category/tag name resolution
        self._categories: dict[int, str] = {}
        self._tags: dict[int, str] = {}

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with optional auth."""
        headers = {"Accept": "application/json", "User-Agent": "Enough/0.1"}
        if self.app_password:
            import base64
            creds = base64.b64encode(f":{self.app_password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"
        return headers

    async def fetch_all_posts(self) -> list[NormalizedPost]:
        """Fetch all published posts with pagination."""
        all_posts: list[NormalizedPost] = []
        page = 1

        async with httpx.AsyncClient(timeout=30, headers=self._get_headers()) as client:
            # Pre-fetch categories and tags
            await self._fetch_taxonomy(client, "categories")
            await self._fetch_taxonomy(client, "tags")

            while True:
                await self.rate_limiter.wait()

                url = f"{self.base_url}/wp-json/wp/v2/posts"
                params = {
                    "per_page": self.per_page,
                    "page": page,
                    "status": "publish",
                    "_fields": "id,title,content,slug,date,modified,link,categories,tags",
                }

                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400:
                        # Past last page
                        break
                    raise

                posts_data = resp.json()
                if not posts_data:
                    break

                total_pages = int(resp.headers.get("X-WP-TotalPages", 1))

                for wp_post in posts_data:
                    normalized = self._normalize_post(wp_post)
                    all_posts.append(normalized)

                logger.info(
                    "WordPress: fetched page %d/%d (%d posts)",
                    page, total_pages, len(posts_data),
                )

                if page >= total_pages:
                    break
                page += 1

        logger.info("WordPress: total %d posts fetched from %s", len(all_posts), self.domain)
        return all_posts

    async def _fetch_taxonomy(self, client: httpx.AsyncClient, taxonomy: str) -> None:
        """Fetch all terms for a taxonomy (categories or tags)."""
        cache = self._categories if taxonomy == "categories" else self._tags
        page = 1

        while True:
            await self.rate_limiter.wait()
            url = f"{self.base_url}/wp-json/wp/v2/{taxonomy}"
            params = {"per_page": 100, "page": page}

            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
            except httpx.HTTPStatusError:
                break

            terms = resp.json()
            if not terms:
                break

            for term in terms:
                cache[term["id"]] = term["name"]

            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1

    def _normalize_post(self, wp_post: dict) -> NormalizedPost:
        """Convert a WordPress REST API post to NormalizedPost."""
        title = wp_post.get("title", {}).get("rendered", "Untitled")
        html_content = wp_post.get("content", {}).get("rendered", "")
        link = wp_post.get("link", "")
        slug = wp_post.get("slug", "")

        # Extract plain text
        soup = BeautifulSoup(html_content, "lxml")
        body_text = soup.get_text(separator=" ", strip=True)

        # Extract internal links
        internal_links = self._extract_internal_links(soup, link)

        # Resolve category/tag names
        cat_ids = wp_post.get("categories", [])
        tag_ids = wp_post.get("tags", [])
        categories = [self._categories[cid] for cid in cat_ids if cid in self._categories]
        tags = [self._tags[tid] for tid in tag_ids if tid in self._tags]

        # Parse dates
        publish_date = _parse_wp_date(wp_post.get("date"))
        modified_date = _parse_wp_date(wp_post.get("modified"))

        # Extract headings structure
        headings = self._extract_headings(soup)

        # Extract meta description (WP REST API excerpt as fallback)
        excerpt_html = wp_post.get("excerpt", {}).get("rendered", "")
        meta_description = None
        if excerpt_html:
            excerpt_soup = BeautifulSoup(excerpt_html, "lxml")
            meta_description = excerpt_soup.get_text(strip=True)[:320] or None

        return NormalizedPost(
            url=link,
            slug=slug,
            title=title,
            body_text=body_text,
            body_html=html_content,
            publish_date=publish_date,
            modified_date=modified_date,
            internal_links=internal_links,
            cms_categories=categories,
            cms_tags=tags,
            word_count=len(body_text.split()),
            content_hash=compute_content_hash(body_text),
            headings=headings,
            meta_description=meta_description,
            http_status=200,
        )

    @staticmethod
    def _extract_headings(soup: BeautifulSoup) -> list[dict[str, str]]:
        """Extract heading structure from HTML content."""
        headings: list[dict[str, str]] = []
        for tag in soup.find_all(re.compile(r"^h[1-6]$")):
            text = tag.get_text(strip=True)
            if text:
                headings.append({"level": tag.name, "text": text})
        return headings

    def _extract_internal_links(self, soup: BeautifulSoup, current_url: str) -> list[InternalLink]:
        """Extract links pointing to the same domain."""
        links: list[InternalLink] = []
        current_parsed = urlparse(current_url)

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            parsed = urlparse(href)

            # Resolve relative URLs
            if not parsed.netloc:
                href = urljoin(current_url, href)
                parsed = urlparse(href)

            # Check same domain
            if parsed.netloc.lower().replace("www.", "") == self.domain.replace("www.", ""):
                anchor_text = anchor.get_text(strip=True)
                links.append(InternalLink(target_url=href, anchor_text=anchor_text or None))

        return links


def _parse_wp_date(date_str: str | None):
    """Parse a WordPress date string to datetime."""
    if not date_str:
        return None
    from datetime import datetime, timezone
    try:
        # WP dates are typically ISO format without timezone (assumed UTC)
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None
