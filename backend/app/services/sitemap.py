"""Universal sitemap crawler.

Parses XML sitemaps (including sitemap index files), fetches each URL,
extracts content using trafilatura, and normalizes to the standard schema.
Supports XML sitemaps, sitemap index, and RSS/Atom fallback.
"""

import asyncio
import logging
import re
from typing import Callable
from urllib.parse import urlparse, urljoin
from xml.etree import ElementTree

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.services.normalizer import NormalizedPost, InternalLink, compute_content_hash
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# XML namespaces
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Common RSS/Atom content types
RSS_CONTENT_TYPES = {"application/rss+xml", "application/atom+xml", "text/xml", "application/xml"}


class SitemapCrawler:
    """Crawl a website via its XML sitemap and extract content."""

    def __init__(
        self,
        sitemap_url: str,
        domain: str,
        delay_seconds: float = 1.0,
        max_pages: int = 5000,
        concurrency: int = 10,
        max_retries: int = 3,
        timeout_seconds: float = 30.0,
        on_progress: Callable[[int, int], None] | None = None,
        url_patterns: list[str] | None = None,
    ):
        self.sitemap_url = sitemap_url
        self.domain = domain.lower()
        # URL patterns to include (e.g. ["/blog/", "/resources/"])
        # If None or empty, all URLs are included
        self.url_patterns: list[str] = [p.lower() for p in url_patterns] if url_patterns else []
        self.rate_limiter = RateLimiter(requests_per_second=1.0 / delay_seconds)
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.on_progress = on_progress

        # Track progress
        self._processed = 0
        self._total = 0
        self._lock = asyncio.Lock()

    async def crawl(self) -> list[NormalizedPost]:
        """Crawl all URLs from the sitemap and extract content concurrently."""
        urls = await self._discover_urls()
        logger.info("Sitemap: found %d URLs for %s", len(urls), self.domain)

        # Apply URL pattern filter (e.g. only /blog/ or /resources/)
        if self.url_patterns:
            before = len(urls)
            from urllib.parse import urlparse as _urlparse
            urls = [
                u for u in urls
                if any(pat in _urlparse(u).path.lower() for pat in self.url_patterns)
            ]
            logger.info(
                "URL pattern filter (%s): %d → %d URLs",
                ", ".join(self.url_patterns), before, len(urls),
            )

        # Limit to max_pages
        if len(urls) > self.max_pages:
            logger.warning(
                "Sitemap has %d URLs, limiting to %d", len(urls), self.max_pages,
            )
            urls = urls[: self.max_pages]

        self._total = len(urls)
        self._processed = 0

        # Process concurrently with semaphore
        semaphore = asyncio.Semaphore(self.concurrency)
        posts: list[NormalizedPost] = []

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "Enough/0.1 (Content Intelligence Bot)"},
            follow_redirects=True,
        ) as client:

            async def _process_url(url: str) -> NormalizedPost | None:
                async with semaphore:
                    await self.rate_limiter.wait()
                    result = await self._fetch_with_retry(client, url)

                    async with self._lock:
                        self._processed += 1
                        if self._processed % 25 == 0 or self._processed == self._total:
                            logger.info(
                                "Sitemap: processed %d/%d URLs",
                                self._processed, self._total,
                            )
                            if self.on_progress:
                                self.on_progress(self._processed, self._total)

                    return result

            tasks = [_process_url(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, NormalizedPost):
                    posts.append(result)
                elif isinstance(result, Exception):
                    logger.warning("Crawl task failed: %s", result)

        logger.info("Sitemap: extracted %d posts from %d URLs", len(posts), len(urls))
        return posts

    async def _discover_urls(self) -> list[str]:
        """Discover URLs: try XML sitemap first, fall back to RSS/Atom."""
        urls: list[str] = []

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "Enough/0.1"},
            follow_redirects=True,
        ) as client:
            # Try the provided sitemap URL
            await self._parse_sitemap_url(client, self.sitemap_url, urls, depth=0)

            # If no URLs found, try common fallback locations
            if not urls:
                base = f"https://{self.domain}"
                fallback_urls = [
                    f"{base}/sitemap.xml",
                    f"{base}/sitemap_index.xml",
                    f"{base}/wp-sitemap.xml",
                    f"{base}/post-sitemap.xml",
                ]
                for fallback in fallback_urls:
                    if fallback != self.sitemap_url:
                        await self._parse_sitemap_url(client, fallback, urls, depth=0)
                        if urls:
                            logger.info("Found URLs via fallback sitemap: %s", fallback)
                            break

            # RSS/Atom fallback
            if not urls:
                rss_urls = await self._try_rss_fallback(client)
                if rss_urls:
                    urls.extend(rss_urls)
                    logger.info("Found %d URLs via RSS/Atom feed", len(rss_urls))

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
            logger.debug("Failed to fetch sitemap %s: %s", url, e)
            return

        try:
            root = ElementTree.fromstring(resp.content)
        except ElementTree.ParseError as e:
            logger.debug("Failed to parse sitemap XML %s: %s", url, e)
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

    async def _try_rss_fallback(self, client: httpx.AsyncClient) -> list[str]:
        """Try to discover post URLs from RSS or Atom feeds."""
        urls: list[str] = []
        base = f"https://{self.domain}"

        feed_locations = [
            f"{base}/feed",
            f"{base}/feed/",
            f"{base}/rss",
            f"{base}/rss.xml",
            f"{base}/atom.xml",
            f"{base}/blog/feed",
            f"{base}/blog/rss",
        ]

        for feed_url in feed_locations:
            try:
                resp = await client.get(feed_url)
                if resp.status_code != 200:
                    continue

                content = resp.text
                try:
                    root = ElementTree.fromstring(resp.content)
                except ElementTree.ParseError:
                    continue

                # RSS 2.0: <channel><item><link>
                for item in root.iter("item"):
                    link_el = item.find("link")
                    if link_el is not None and link_el.text:
                        urls.append(link_el.text.strip())

                # Atom: <entry><link href="...">
                for entry in root.findall("atom:entry", ATOM_NS):
                    link_el = entry.find("atom:link[@rel='alternate']", ATOM_NS)
                    if link_el is None:
                        link_el = entry.find("atom:link", ATOM_NS)
                    if link_el is not None:
                        href = link_el.get("href")
                        if href:
                            urls.append(href.strip())

                # Also check without namespace (common in RSS)
                if not urls:
                    for entry in root.iter("entry"):
                        for link_el in entry.iter("link"):
                            href = link_el.get("href")
                            if href and href.startswith("http"):
                                urls.append(href.strip())

                if urls:
                    return urls

            except Exception as e:
                logger.debug("RSS fallback failed for %s: %s", feed_url, e)
                continue

        return urls

    async def _fetch_with_retry(
        self, client: httpx.AsyncClient, url: str
    ) -> NormalizedPost | None:
        """Fetch a URL with retry logic."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                return await self._fetch_and_extract(client, url)
            except httpx.TimeoutException as e:
                last_error = e
                logger.debug(
                    "Timeout fetching %s (attempt %d/%d)",
                    url, attempt + 1, self.max_retries,
                )
                await asyncio.sleep(1.0 * (attempt + 1))
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503, 504):
                    last_error = e
                    wait = 2.0 * (attempt + 1)
                    logger.debug(
                        "HTTP %d from %s, retrying in %.1fs",
                        e.response.status_code, url, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.warning("HTTP %d from %s, not retrying", e.response.status_code, url)
                    return None
            except Exception as e:
                logger.warning("Failed to process %s: %s", url, e)
                return None

        logger.warning("Max retries exceeded for %s: %s", url, last_error)
        return None

    async def _fetch_and_extract(
        self, client: httpx.AsyncClient, url: str
    ) -> NormalizedPost | None:
        """Fetch a page and extract content using trafilatura."""
        resp = await client.get(url)
        resp.raise_for_status()

        html = resp.text
        http_status = resp.status_code

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

        # Extract headings structure as JSON array
        headings = self._extract_headings(soup)

        # Extract meta description
        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
        meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

        # Extract HTML of main content area — preserve images and structure
        # Use BeautifulSoup to find the main content area instead of trafilatura XML
        # (trafilatura XML strips media elements like <img>, <picture>, <figure>)
        main_content = soup.find("main") or soup.find("article") or soup.find("div", class_=lambda c: c and ("content" in c.lower() or "post" in c.lower() or "entry" in c.lower())) or soup.find("body")
        body_html = str(main_content) if main_content else html

        # Extract internal links from full page HTML
        internal_links = self._extract_internal_links(soup, url)

        # Extract slug from URL
        parsed = urlparse(url)
        slug = parsed.path.strip("/").split("/")[-1] if parsed.path.strip("/") else None

        # Attempt to find publish/modified dates via trafilatura metadata + meta tags
        metadata = trafilatura.extract_metadata(html)
        publish_date = None
        modified_date = None

        if metadata and metadata.date:
            from datetime import datetime, timezone
            try:
                publish_date = datetime.fromisoformat(str(metadata.date)).replace(
                    tzinfo=timezone.utc
                )
            except (ValueError, TypeError):
                pass

        # Extract language from <html lang="..."> or hreflang meta
        language: str | None = None
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            language = str(html_tag["lang"]).split("-")[0].lower()[:10]  # e.g. "en" from "en-US"
        if not language:
            hreflang = soup.find("link", attrs={"rel": "alternate", "hreflang": True})
            if hreflang and hreflang.get("hreflang") and hreflang["hreflang"] != "x-default":
                language = str(hreflang["hreflang"]).split("-")[0].lower()[:10]

        # Extract modified_date from meta tags (trafilatura doesn't always get it)
        from datetime import datetime, timezone
        modified_meta = (
            soup.find("meta", attrs={"property": "article:modified_time"})
            or soup.find("meta", attrs={"property": "og:updated_time"})
            or soup.find("meta", attrs={"name": "last-modified"})
            or soup.find("meta", attrs={"itemprop": "dateModified"})
        )
        if modified_meta and modified_meta.get("content"):
            try:
                modified_date = datetime.fromisoformat(
                    modified_meta["content"].replace("Z", "+00:00")
                ).replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        # Also try to extract publish_date from meta if trafilatura missed it
        if not publish_date:
            pub_meta = (
                soup.find("meta", attrs={"property": "article:published_time"})
                or soup.find("meta", attrs={"property": "og:published_time"})
                or soup.find("meta", attrs={"itemprop": "datePublished"})
            )
            if pub_meta and pub_meta.get("content"):
                try:
                    publish_date = datetime.fromisoformat(
                        pub_meta["content"].replace("Z", "+00:00")
                    ).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

        # Extract time tags as fallback (common in blog templates)
        if not publish_date or not modified_date:
            time_tags = soup.find_all("time", attrs={"datetime": True})
            for tt in time_tags:
                try:
                    dt = datetime.fromisoformat(
                        tt["datetime"].replace("Z", "+00:00")
                    ).replace(tzinfo=timezone.utc)
                    classes = tt.get("class", [])
                    if isinstance(classes, str):
                        classes = [classes]
                    cls_str = " ".join(classes).lower()
                    if not publish_date and ("publish" in cls_str or "created" in cls_str or "entry-date" in cls_str):
                        publish_date = dt
                    elif not modified_date and ("modif" in cls_str or "update" in cls_str):
                        modified_date = dt
                    elif not publish_date:
                        publish_date = dt  # First time tag as fallback
                except (ValueError, TypeError):
                    pass

        return NormalizedPost(
            url=url,
            slug=slug,
            title=title,
            body_text=body_text,
            body_html=body_html,
            publish_date=publish_date,
            modified_date=modified_date,
            internal_links=internal_links,
            cms_categories=[],
            cms_tags=[],
            word_count=len(body_text.split()),
            content_hash=compute_content_hash(body_text),
            headings=headings,
            meta_description=meta_description,
            http_status=http_status,
            language=language,
        )

    @staticmethod
    def _extract_headings(soup: BeautifulSoup) -> list[dict[str, str]]:
        """Extract heading structure as [{level: "h2", text: "Section Title"}, ...]."""
        headings: list[dict[str, str]] = []
        for tag in soup.find_all(re.compile(r"^h[1-6]$")):
            text = tag.get_text(strip=True)
            if text:
                headings.append({"level": tag.name, "text": text})
        return headings

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
