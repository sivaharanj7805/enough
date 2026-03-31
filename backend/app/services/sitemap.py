"""Universal sitemap crawler.

Parses XML sitemaps (including sitemap index files), fetches each URL,
extracts content using trafilatura, and normalizes to the standard schema.
Supports XML sitemaps, sitemap index, and RSS/Atom fallback.
"""

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx
import trafilatura
from bs4 import BeautifulSoup

from app.services.normalizer import InternalLink, NormalizedPost, compute_content_hash
from app.utils.rate_limiter import RateLimiter, get_domain_limiter

logger = logging.getLogger(__name__)

# XML namespaces
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Common RSS/Atom content types
RSS_CONTENT_TYPES = {"application/rss+xml", "application/atom+xml", "text/xml", "application/xml"}


def _extract_eeat_metadata(soup: BeautifulSoup) -> dict:
    """Extract E-E-A-T signals from full page HTML during crawl.

    These signals live in page chrome (header, footer, <head>) that isn't
    included in body_html. Extracted here so Step 2 E-E-A-T scoring has
    access to them without needing the full page HTML.
    """
    signals: dict = {}

    # Author name — from meta tag (most reliable), then byline div, then author link
    meta_author = soup.find("meta", attrs={"name": "author"})
    if meta_author and meta_author.get("content"):
        signals["author_name"] = meta_author["content"].strip()[:60]
    else:
        byline = soup.find("div", class_=re.compile(r"post-author|byline|entry-author", re.I))
        if byline:
            a = byline.find("a")
            if a:
                signals["author_name"] = a.get_text(strip=True)[:60]
        if "author_name" not in signals:
            author_a = soup.find("a", href=re.compile(r"/authors?/[^/]+", re.I))
            if author_a and author_a.get_text(strip=True):
                signals["author_name"] = author_a.get_text(strip=True)[:60]

    # Schema types from JSON-LD
    schema_types = []
    has_author_schema = False
    for st in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            import json as _json
            data = _json.loads(st.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    stype = item.get("@type", "")
                    if isinstance(stype, list):
                        schema_types.extend(stype)
                    elif stype:
                        schema_types.append(stype)
                    if "author" in item:
                        has_author_schema = True
        except Exception:
            continue
    signals["schema_types"] = schema_types
    signals["has_author_schema"] = has_author_schema

    # Visible date signals (time tags, meta dates, date-class elements, text patterns)
    has_visible_date = bool(soup.find("time", attrs={"datetime": True}))
    if not has_visible_date:
        for meta_name in ["article:published_time", "article:modified_time"]:
            if soup.find("meta", attrs={"property": meta_name}):
                has_visible_date = True
                break
    # Check for date-class elements (common in WordPress themes)
    if not has_visible_date:
        date_el = soup.find(True, class_=re.compile(r"date|entry-date|post-date|published|pubdate", re.I))
        if date_el and date_el.get_text(strip=True):
            has_visible_date = True
    # Check for visible date text patterns in first 3000 chars of page
    if not has_visible_date:
        page_text = soup.get_text(" ", strip=True)[:3000]
        if re.search(
            r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z.]*\s+\d{1,2},?\s+\d{4})"
            r"|(?:published|posted|updated|modified)\s*[:\s]*\d",
            page_text, re.IGNORECASE,
        ):
            has_visible_date = True
    signals["has_visible_date"] = has_visible_date

    # About/contact links
    all_links = soup.find_all("a", href=True)
    signals["has_contact_link"] = any(
        any(kw in str(a.get("href", "")).lower() or kw in a.get_text().lower()
            for kw in ["contact", "about", "team"])
        for a in all_links
    )

    # Credible external links
    credible_domains = ["gov", "edu", "who.int", "nature.com", "pubmed",
                        "harvard.edu", "mit.edu", "stanford.edu", "reuters.com"]
    signals["credible_link_count"] = sum(
        1 for a in all_links
        if any(d in str(a.get("href", "")).lower() for d in credible_domains)
    )

    # S4-05: Technical SEO head signals (canonical, OG, JSON-LD)
    # These live in <head>, not in body_html. Extracted here so health scoring
    # can check them without needing the full page HTML.
    signals["has_og_tags"] = bool(soup.find("meta", attrs={"property": re.compile(r"^og:")}))
    signals["has_canonical"] = bool(soup.find("link", attrs={"rel": "canonical"}))
    signals["has_jsonld"] = len(schema_types) > 0

    return signals


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
        self._delay_rps = 1.0 / delay_seconds
        self.rate_limiter: RateLimiter | None = None  # resolved in crawl()
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.on_progress = on_progress

        # Track progress
        self._processed = 0
        self._total = 0
        self._lock = asyncio.Lock()
        self._skipped: list[tuple[str, str]] = []  # (url, reason)
        self._canonical_redirects: list[tuple[str, str]] = []  # (original_url, canonical_url)
        self._robots_filtered: int = 0
        self._robots_rules: list[str] = []  # disallow rules from robots.txt

    async def crawl(self) -> list[NormalizedPost]:
        """Crawl all URLs from the sitemap and extract content concurrently."""
        # Use a shared per-domain rate limiter so concurrent crawls to the same
        # domain (e.g. two users auditing sites on the same shared host) don't
        # multiply the request rate and get us blocked.
        self.rate_limiter = await get_domain_limiter(self.domain, self._delay_rps)

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

        # Filter URLs disallowed by robots.txt
        urls = await self._filter_robots_txt(urls)

        # Limit to max_pages. Sort by URL path depth first so that shorter
        # paths (more likely to be important hub/pillar pages) survive truncation.
        # Sitemap order is arbitrary (alphabetical, chronological, random) so
        # blindly taking the first N can miss important content.
        if len(urls) > self.max_pages:
            logger.warning(
                "Sitemap has %d URLs, limiting to %d (sorted by path depth)",
                len(urls), self.max_pages,
            )
            urls.sort(key=lambda u: urlparse(u).path.count("/"))
            urls = urls[: self.max_pages]

        self._total = len(urls)
        self._processed = 0
        self._skipped = []
        self._canonical_redirects = []

        # Process concurrently with semaphore
        semaphore = asyncio.Semaphore(self.concurrency)
        posts: list[NormalizedPost] = []

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "Tended/0.1 (Content Intelligence Bot)"},
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

        skipped_count = len(self._skipped)
        if skipped_count > 0:
            logger.info(
                "Sitemap: skipped %d URLs out of %d total. Reasons: %s",
                skipped_count, len(urls),
                ", ".join(f"{reason}: {sum(1 for _, r in self._skipped if r == reason)}"
                          for reason in sorted(set(r for _, r in self._skipped))),
            )
            # Log first 10 skipped URLs at debug level for investigation
            for skip_url, reason in self._skipped[:10]:
                logger.debug("Skipped: %s — %s", skip_url, reason)

        logger.info(
            "Sitemap: extracted %d posts from %d URLs (%d skipped)",
            len(posts), len(urls), skipped_count,
        )
        return posts

    async def _discover_urls(self) -> list[str]:
        """Discover URLs: try XML sitemap first, fall back to RSS/Atom."""
        urls: list[str] = []

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            headers={"User-Agent": "Tended/0.1"},
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

    async def _filter_robots_txt(self, urls: list[str]) -> list[str]:
        """Filter out URLs disallowed by robots.txt for our user-agent.

        Fetches /robots.txt once, parses disallow rules, and removes
        matching URLs. If robots.txt is unreachable, all URLs are kept
        (permissive fallback — don't block crawling on robots.txt errors).
        """
        from urllib.robotparser import RobotFileParser

        robots_url = f"https://{self.domain}/robots.txt"
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(robots_url)
                if resp.status_code != 200:
                    return urls  # No robots.txt — all URLs allowed

            parser = RobotFileParser()
            lines = resp.text.splitlines()
            parser.parse(lines)

            # Extract disallow rules for diagnostics
            self._robots_rules = [
                line.strip() for line in lines
                if line.strip().lower().startswith("disallow:")
            ]

            before = len(urls)
            allowed = [u for u in urls if parser.can_fetch("Tended", u)]
            blocked_urls = [u for u in urls if not parser.can_fetch("Tended", u)]

            self._robots_filtered = len(blocked_urls)
            if blocked_urls:
                logger.info(
                    "robots.txt: filtered %d disallowed URLs (kept %d of %d)",
                    len(blocked_urls), len(allowed), before,
                )
                for bu in blocked_urls[:5]:
                    logger.debug("robots.txt blocked: %s", bu)
            return allowed

        except Exception as e:
            logger.debug("robots.txt fetch/parse failed for %s: %s (proceeding with all URLs)", self.domain, e)
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
                    async with self._lock:
                        self._skipped.append((url, f"http_{e.response.status_code}"))
                    return None
            except Exception as e:
                logger.warning("Failed to process %s: %s", url, e)
                async with self._lock:
                    self._skipped.append((url, f"error: {type(e).__name__}"))
                return None

        logger.warning("Max retries exceeded for %s: %s", url, last_error)
        async with self._lock:
            self._skipped.append((url, "max_retries_exceeded"))
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

        # SPA fallback: if trafilatura got empty but page has JS framework markers, try Playwright
        if (not body_text or len(body_text.strip()) < 50) and html:
            js_markers = ['id="root"', 'id="app"', 'id="__next"', 'data-reactroot', '_nuxt', 'id="__nuxt"']
            if any(marker in html for marker in js_markers):
                rendered = await self._render_with_playwright(url)
                if rendered:
                    body_text = trafilatura.extract(rendered) or ""
                    if body_text and len(body_text.strip()) >= 50:
                        html = rendered
                        logger.info("Playwright fallback succeeded for %s (%d chars)", url, len(body_text))

        if not body_text or len(body_text.strip()) < 50:
            reason = "body_text_empty" if not body_text else f"body_text_too_short ({len(body_text.strip())} chars)"
            async with self._lock:
                self._skipped.append((url, reason))
            return None

        # Word count floor: 100 words minimum to be worth analyzing.
        # The 50-char gate above catches truly empty pages, but lets through
        # 18-word "Thank You" pages and 19-word login redirects. A 100-word
        # floor ensures every post in the dataset has at least a paragraph
        # of real content for downstream analysis (health scoring, readability,
        # thin content detection all depend on meaningful word count).
        word_count = len(body_text.split())
        if word_count < 100:
            async with self._lock:
                self._skipped.append((url, f"too_few_words ({word_count} words)"))
            return None

        # Parse full page HTML
        soup = BeautifulSoup(html, "lxml")

        # ── Canonical URL resolution ──
        # If the page declares a canonical URL on the same domain, use it
        # instead of the fetched URL. Prevents duplicates from URL variants.
        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        if canonical_tag and canonical_tag.get("href"):
            canonical_href = canonical_tag["href"].strip()
            canonical_parsed = urlparse(canonical_href)
            # Only use canonical if it's on the same domain (not cross-domain canonicals)
            canonical_domain = canonical_parsed.netloc.lower().replace("www.", "")
            if canonical_domain == self.domain.replace("www.", "") and canonical_href != url:
                logger.debug("Canonical redirect: %s → %s", url, canonical_href)
                async with self._lock:
                    self._canonical_redirects.append((url, canonical_href))
                url = canonical_href

        # Extract title (from full page — title tag is in <head>)
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else url

        # Extract meta description (from full page — meta tags are in <head>)
        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
        meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

        # ── Extract E-E-A-T metadata from full page HTML ──
        # These signals live in page chrome (header, footer, <head>), not article body.
        # body_html only contains the article content area, so E-E-A-T scoring in
        # Step 2 can't see them. Extract now and carry as metadata on the post.
        eeat_signals = _extract_eeat_metadata(soup)

        # Identify the main content area — used for body_html, headings, and links.
        # Everything below extracts from this element, NOT the full page HTML,
        # to exclude sidebar, header, footer, and nav template elements.
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=lambda c: c and (
                "content" in c.lower() or "post" in c.lower() or "entry" in c.lower()
            ))
            or soup.find("body")
        )
        body_html = str(main_content) if main_content else html

        # Extract headings from main content only — NOT full page HTML.
        # Extracting from soup would include sidebar headings ("Primary Sidebar",
        # "You might also like"), footer CTAs, and nav items. These pollute
        # heading analysis metrics (e.g. "13% question-format H2s" gets diluted
        # by non-article headings in the denominator).
        headings = self._extract_headings(main_content if main_content else soup)

        # Extract internal links from main content area only (not full page HTML).
        # This avoids sidebar widgets ("Popular Posts", "Related Content") that appear
        # on 50-79% of pages inflating inbound link counts and masking orphaned posts.
        internal_links = self._extract_internal_links(
            main_content if main_content else soup, url,
        )

        # Extract slug from URL
        parsed = urlparse(url)
        slug = parsed.path.strip("/").split("/")[-1] if parsed.path.strip("/") else None

        # ── Date extraction ──
        # Strategy: structured metadata only. No catch-all "first <time> tag" fallback,
        # which can grab dates from article body content and corrupt freshness scoring.
        from datetime import datetime

        publish_date = None
        modified_date = None

        # Try trafilatura metadata first
        metadata = trafilatura.extract_metadata(html)
        if metadata and metadata.date:
            try:
                publish_date = datetime.fromisoformat(str(metadata.date)).replace(
                    tzinfo=UTC
                )
            except (ValueError, TypeError):
                pass

        # Extract modified_date from meta tags (trafilatura doesn't always get it)
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
                ).replace(tzinfo=UTC)
            except (ValueError, TypeError):
                pass

        # Try structured publish_date meta tags if trafilatura missed it
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
                    ).replace(tzinfo=UTC)
                except (ValueError, TypeError):
                    pass

        # Try <time> tags, but ONLY those with explicit semantic class names.
        # Do NOT use unclassified <time> tags as a catch-all — they may contain
        # dates from article body content (e.g. "This study was conducted in 2023").
        if not publish_date or not modified_date:
            time_tags = soup.find_all("time", attrs={"datetime": True})
            for tt in time_tags:
                try:
                    dt = datetime.fromisoformat(
                        tt["datetime"].replace("Z", "+00:00")
                    ).replace(tzinfo=UTC)
                    classes = tt.get("class", [])
                    if isinstance(classes, str):
                        classes = [classes]
                    cls_str = " ".join(classes).lower()
                    if not publish_date and ("publish" in cls_str or "created" in cls_str or "entry-date" in cls_str):
                        publish_date = dt
                    elif not modified_date and ("modif" in cls_str or "update" in cls_str):
                        modified_date = dt
                    # REMOVED: catch-all "elif not publish_date: publish_date = dt"
                    # That fallback grabbed dates from body content and corrupted freshness data.
                except (ValueError, TypeError):
                    pass

        # Extract language from <html lang="..."> or hreflang meta
        language: str | None = None
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            language = str(html_tag["lang"]).split("-")[0].lower()[:10]
        if not language:
            hreflang = soup.find("link", attrs={"rel": "alternate", "hreflang": True})
            if hreflang and hreflang.get("hreflang") and hreflang["hreflang"] != "x-default":
                language = str(hreflang["hreflang"]).split("-")[0].lower()[:10]

        # Classify page type from URL + HTML
        from app.services.page_type_classifier import classify_page_type
        page_type = classify_page_type(url, body_html, headings)

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
            word_count=word_count,
            content_hash=compute_content_hash(body_text),
            headings=headings,
            meta_description=meta_description,
            http_status=http_status,
            language=language,
            page_type=page_type,
            eeat_signals=eeat_signals,
        )

    _playwright_sem = asyncio.Semaphore(3)

    async def _render_with_playwright(self, url: str) -> str | None:
        """Render a JS-heavy page with headless Chromium. Returns HTML or None."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None  # Playwright not installed — skip gracefully

        async with self._playwright_sem:
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=15000)
                    html = await page.content()
                    await browser.close()
                    return html
            except Exception as e:
                logger.debug("Playwright render failed for %s: %s", url, e)
                return None

    @staticmethod
    def _extract_headings(soup: BeautifulSoup) -> list[dict[str, str]]:
        """Extract heading structure as [{level: "h2", text: "Section Title"}, ...].

        Filters out likely author bylines styled as headings (common in WP themes):
        H4-H6 tags with 1-3 words that are all Title Case (e.g., "Brian Clark").
        """
        headings: list[dict[str, str]] = []
        for tag in soup.find_all(re.compile(r"^h[1-6]$")):
            text = tag.get_text(strip=True)
            if not text:
                continue
            # Filter author bylines: H4-H6 headings that are short proper names.
            # "Brian Clark" (2 words, title case, H4) → byline, skip.
            # "How to Build Links" (4 words, H4) → real heading, keep.
            level_num = int(tag.name[1])
            words = text.split()
            if level_num >= 4 and len(words) <= 3:
                # Check if all words are Title Case (proper name pattern)
                if all(w[0].isupper() and w[1:].islower() for w in words if len(w) > 1):
                    continue
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
