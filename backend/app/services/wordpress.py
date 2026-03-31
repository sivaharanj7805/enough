"""WordPress REST API connector.

Fetches all published posts from a WordPress site, resolves categories/tags,
extracts internal links, and normalizes to the standard schema.
"""

import logging
import re
from datetime import UTC
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.normalizer import InternalLink, NormalizedPost, compute_content_hash
from app.services.page_type_classifier import classify_page_type
from app.utils.rate_limiter import RateLimiter, get_domain_limiter

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
        self.rate_limiter: RateLimiter | None = None  # resolved in fetch_all_posts()

        # Caches for category/tag name resolution
        self._categories: dict[int, str] = {}
        self._tags: dict[int, str] = {}

    def _get_headers(self) -> dict[str, str]:
        """Build request headers with optional auth."""
        headers = {"Accept": "application/json", "User-Agent": "Tended/0.1"}
        if self.app_password:
            import base64
            creds = base64.b64encode(f":{self.app_password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"
        return headers

    async def fetch_all_posts(self) -> list[NormalizedPost]:
        """Fetch all published posts (and pages, if significant) with pagination."""
        # Use shared per-domain rate limiter across concurrent crawls
        self.rate_limiter = await get_domain_limiter(self.domain, 5.0)

        all_posts: list[NormalizedPost] = []

        async with httpx.AsyncClient(timeout=30, headers=self._get_headers()) as client:
            # Pre-fetch categories and tags
            await self._fetch_taxonomy(client, "categories")
            await self._fetch_taxonomy(client, "tags")

            # Fetch all posts
            posts_fetched = await self._fetch_content_type(client, "posts", all_posts)

            # Auto-detect WP pages: if the site has a significant number of
            # published pages (>10% of post count or >5 absolute), fetch them too.
            # Cornerstone content is often published as WP "pages" not "posts."
            try:
                await self.rate_limiter.wait()
                resp = await client.get(
                    f"{self.base_url}/wp-json/wp/v2/pages",
                    params={"per_page": 1, "status": "publish"},
                )
                if resp.status_code == 200:
                    total_pages_count = int(resp.headers.get("X-WP-Total", 0))
                    threshold = max(5, int(posts_fetched * 0.1))
                    if total_pages_count >= threshold:
                        logger.info(
                            "WordPress: found %d pages (threshold %d) — fetching",
                            total_pages_count, threshold,
                        )
                        await self._fetch_content_type(client, "pages", all_posts)
                    elif total_pages_count > 0:
                        logger.info(
                            "WordPress: skipping %d pages (below threshold %d)",
                            total_pages_count, threshold,
                        )
            except Exception as e:
                logger.debug("WP pages detection failed (non-fatal): %s", e)

        # Enrich posts with language + page_type from actual permalink HTML.
        # WP API doesn't expose <html lang> or page structure, so we fetch
        # a sample of permalinks concurrently to fill these fields.
        await self._enrich_from_html(all_posts)

        logger.info("WordPress: total %d content items fetched from %s", len(all_posts), self.domain)
        return all_posts

    async def _fetch_content_type(
        self,
        client: httpx.AsyncClient,
        content_type: str,
        results: list[NormalizedPost],
    ) -> int:
        """Fetch all items of a WP content type (posts or pages). Returns count."""
        page = 1
        count = 0

        while True:
            await self.rate_limiter.wait()

            url = f"{self.base_url}/wp-json/wp/v2/{content_type}"
            fields = "id,title,content,excerpt,slug,date,modified,link,yoast_head_json"
            if content_type == "posts":
                fields += ",categories,tags"
            params = {
                "per_page": self.per_page,
                "page": page,
                "status": "publish",
                "_fields": fields,
            }

            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    break
                raise

            items = resp.json()
            if not items:
                break

            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))

            for wp_item in items:
                normalized = self._normalize_post(wp_item)
                results.append(normalized)
                count += 1

            logger.info(
                "WordPress %s: fetched page %d/%d (%d items)",
                content_type, page, total_pages, len(items),
            )

            if page >= total_pages:
                break
            page += 1

        return count

    async def _enrich_from_html(self, posts: list[NormalizedPost]) -> None:
        """Fetch actual permalink HTML to extract language and page_type.

        WP REST API doesn't expose <html lang> or page structure signals,
        so we fetch a small sample to detect site language (applied to all posts)
        and classify each post's page_type from URL patterns + HTML signals.
        """
        if not posts:
            return

        # Detect site language from first successful fetch (same for all posts on the site)
        site_language: str | None = None
        sample_url = posts[0].url

        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={"User-Agent": "Tended/0.1"},
                follow_redirects=True,
            ) as client:
                resp = await client.get(sample_url)
                if resp.status_code == 200:
                    sample_soup = BeautifulSoup(resp.text, "lxml")
                    html_tag = sample_soup.find("html")
                    if html_tag and html_tag.get("lang"):
                        site_language = str(html_tag["lang"]).split("-")[0].lower()[:10]
                    if not site_language:
                        hreflang = sample_soup.find("link", attrs={"rel": "alternate", "hreflang": True})
                        if hreflang and hreflang.get("hreflang") and hreflang["hreflang"] != "x-default":
                            site_language = str(hreflang["hreflang"]).split("-")[0].lower()[:10]
        except Exception as e:
            logger.debug("Language detection fetch failed for %s: %s", sample_url, e)

        # Apply language + page_type to all posts
        for post in posts:
            post.language = site_language
            post.page_type = classify_page_type(post.url, post.body_html, post.headings)

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

        # Extract meta description: prefer SEO plugin data over WP excerpt.
        # Yoast SEO exposes yoast_head_json.description with the actual meta tag value.
        # RankMath uses the same field when the Yoast compat layer is active.
        meta_description = None
        yoast = wp_post.get("yoast_head_json") or {}
        if isinstance(yoast, dict):
            meta_description = (yoast.get("description") or "").strip()[:320] or None
            # Also try og:description if main description is empty
            if not meta_description:
                og = yoast.get("og_description") or ""
                meta_description = og.strip()[:320] or None

        # Fallback: WP excerpt (often auto-generated from first paragraph)
        if not meta_description:
            excerpt_html = wp_post.get("excerpt", {}).get("rendered", "")
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
        urlparse(current_url)

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
    from datetime import datetime
    try:
        # WP dates are typically ISO format without timezone (assumed UTC)
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return None
