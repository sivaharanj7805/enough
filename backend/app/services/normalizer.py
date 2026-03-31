"""Content normalization layer.

Both WordPress and sitemap ingestion paths produce NormalizedPost objects,
which are then stored uniformly in the database.
"""

import hashlib
import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import asyncpg

from app.utils.url_normalize import normalize_url

logger = logging.getLogger(__name__)

# Common site name separators in titles — require spaces around separator
# to avoid splitting on hyphens within words/titles like "auto-retry"
_TITLE_SEPARATORS = re.compile(r"\s+[|–—]\s+|\s+-\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_site_name_from_title(title: str) -> str:
    """Remove trailing ' | Site Name' or ' - Site Name' from titles.

    Heuristic: split on separators, drop the last segment if it looks
    like a site/brand name (≤4 words, appears at the end).
    """
    if not title:
        return title
    # Split on common separators
    parts = _TITLE_SEPARATORS.split(title)
    if len(parts) >= 2:
        last = parts[-1].strip()
        # If last segment is short (<=4 words), it's likely a site name
        # Take everything except the last part (which is usually the site name)
        if len(last.split()) <= 4:
            title = _TITLE_SEPARATORS.split(title, maxsplit=1)[0].strip()
    return title


def _strip_html_from_meta(text: str | None) -> str | None:
    """Remove HTML tags from meta descriptions."""
    if not text:
        return text
    cleaned = _HTML_TAG_RE.sub("", text).strip()
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned if cleaned else None


def filter_nav_links(
    all_posts_links: dict[str, list["InternalLink"]],
    threshold: float = 0.8,
) -> dict[str, list["InternalLink"]]:
    """Filter out site-wide navigation links that appear on most pages.

    Args:
        all_posts_links: mapping of post_url → list of InternalLinks
        threshold: if a target_url appears in ≥ this fraction of posts, it's nav

    Returns:
        Filtered mapping with nav links removed.
    """
    if not all_posts_links:
        return all_posts_links

    total_posts = len(all_posts_links)
    if total_posts < 3:
        return all_posts_links  # Too few posts to detect nav patterns

    # Count how many posts link to each target URL
    target_counts: Counter[str] = Counter()
    for links in all_posts_links.values():
        # Deduplicate within a single post
        seen = set()
        for link in links:
            norm = link.target_url.rstrip("/").lower()
            if norm not in seen:
                target_counts[norm] += 1
                seen.add(norm)

    # URLs appearing in ≥ threshold fraction of posts are nav links
    nav_urls: set[str] = set()
    for url, count in target_counts.items():
        if count / total_posts >= threshold:
            nav_urls.add(url)

    if nav_urls:
        logger.info(
            "Detected %d navigation URLs (appearing in ≥%.0f%% of %d posts)",
            len(nav_urls), threshold * 100, total_posts,
        )

    # Filter
    filtered = {}
    for post_url, links in all_posts_links.items():
        filtered[post_url] = [
            link for link in links
            if link.target_url.rstrip("/").lower() not in nav_urls
        ]

    return filtered


def filter_sitewide_headings(
    all_posts_headings: dict[str, list[dict[str, str]]],
    h1_threshold: float = 0.8,
    h2_plus_threshold: float = 0.9,
) -> dict[str, list[dict[str, str]]]:
    """Remove headings that appear on almost every page (template chrome).

    Two-tier thresholds:
    - H1 at 80%: catches site name headings (common in header/nav).
    - H2-H6 at 90%: catches template headings like "Reader Interactions",
      "You might also like", "Leave a Reply" that leak from comment sections
      or widgets. The stricter threshold avoids filtering legitimate repeated
      article sections like "Summary" or "Conclusion" which typically appear
      on 30-60% of posts, not 90%+.

    Args:
        all_posts_headings: mapping of post_url → list of heading dicts
        h1_threshold: fraction for H1 headings (default 0.8)
        h2_plus_threshold: fraction for H2-H6 headings (default 0.9)

    Returns:
        Filtered mapping with sitewide headings removed.
    """
    if not all_posts_headings:
        return all_posts_headings

    total_posts = len(all_posts_headings)
    if total_posts < 3:
        return all_posts_headings

    # Count heading occurrences by level
    counts_by_level: dict[str, Counter[str]] = {}
    for headings in all_posts_headings.values():
        seen: set[tuple[str, str]] = set()
        for h in headings:
            text = h.get("text", "").strip().lower()
            level = str(h.get("level", "h2"))
            if text and (level, text) not in seen:
                if level not in counts_by_level:
                    counts_by_level[level] = Counter()
                counts_by_level[level][text] += 1
                seen.add((level, text))

    # Build the set of sitewide headings to remove
    sitewide: set[str] = set()

    # H1: 80% threshold
    for text, count in counts_by_level.get("h1", {}).items():
        if count / total_posts >= h1_threshold:
            sitewide.add(text)

    # H2-H6: 90% threshold (stricter to protect legitimate repeated sections)
    for level in ("h2", "h3", "h4", "h5", "h6"):
        for text, count in counts_by_level.get(level, {}).items():
            if count / total_posts >= h2_plus_threshold:
                sitewide.add(text)

    if sitewide:
        logger.info(
            "Detected %d sitewide headings (H1≥%.0f%%, H2+≥%.0f%% of %d posts): %s",
            len(sitewide), h1_threshold * 100, h2_plus_threshold * 100, total_posts,
            ", ".join(f'"{h}"' for h in list(sitewide)[:5]),
        )

    # Filter
    filtered = {}
    for post_url, headings in all_posts_headings.items():
        filtered[post_url] = [
            h for h in headings
            if h.get("text", "").strip().lower() not in sitewide
        ]

    return filtered


@dataclass
class InternalLink:
    """A link found in post HTML pointing to the same domain."""
    target_url: str
    anchor_text: str | None = None


@dataclass
class NormalizedPost:
    """Unified post representation from any CMS or crawler."""
    url: str
    title: str
    body_text: str
    body_html: str
    slug: str | None = None
    publish_date: datetime | None = None
    modified_date: datetime | None = None
    internal_links: list[InternalLink] = field(default_factory=list)
    cms_categories: list[str] = field(default_factory=list)
    cms_tags: list[str] = field(default_factory=list)
    # E-E-A-T metadata extracted from full page HTML during crawl.
    # body_html only contains the article content area, but E-E-A-T signals
    # (author byline, meta tags, schema, about links) live in the page chrome.
    # These are extracted at crawl time and stored as JSONB for Step 2 scoring.
    eeat_signals: dict = field(default_factory=dict)
    word_count: int = 0
    content_hash: str = ""
    headings: list[dict[str, str]] = field(default_factory=list)
    meta_description: str | None = None
    http_status: int | None = None
    language: str | None = None
    page_type: str = "blog"

    def __post_init__(self):
        if not self.word_count and self.body_text:
            self.word_count = len(self.body_text.split())
        if not self.content_hash and self.body_text:
            self.content_hash = compute_content_hash(self.body_text)


def compute_content_hash(text: str) -> str:
    """SHA256 hash of content for change detection.

    Normalizes whitespace before hashing so that minor extraction differences
    (e.g. trafilatura version upgrade producing slightly different spacing)
    don't trigger unnecessary re-embedding of unchanged content.
    """
    normalized = " ".join(text.split())  # collapse all whitespace to single spaces
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def save_normalized_posts(
    db: asyncpg.Connection,
    site_id: UUID,
    posts: list[NormalizedPost],
) -> int:
    """Upsert normalized posts and their internal links into the database.

    Returns the number of posts saved.

    Note: All page types (blog, product, documentation, landing, glossary, index)
    are stored. Downstream steps (health scoring, problem detection, recommendations)
    should filter by page_type when appropriate — e.g. exclude "landing" and "index"
    pages from content-quality analysis, as these are structural pages (homepages,
    category pages) that don't benefit from blog-oriented advice like "add H2 headings."
    """
    saved = 0

    # ── Check subscription post limit ──
    try:
        from app.services.stripe_service import StripeService
        service = StripeService()
        site_row = await db.fetchrow("SELECT user_id FROM sites WHERE id = $1", site_id)
        if site_row and site_row["user_id"]:
            user_id = str(site_row["user_id"])
            limits = await service._get_tier_limits(db, user_id)
            post_limit = limits.get("posts", 0)
            if post_limit > 0:
                existing_count = await db.fetchval(
                    "SELECT COUNT(*) FROM posts p JOIN sites s ON p.site_id = s.id WHERE s.user_id = $1",
                    user_id,
                )
                remaining = max(0, post_limit - (existing_count or 0))
                if remaining < len(posts):
                    logger.warning(
                        "Post limit: user %s has %d/%d posts, truncating crawl to %d",
                        user_id, existing_count, post_limit, remaining,
                    )
                    posts = posts[:remaining]
    except Exception as e:
        logger.warning("Post limit check failed (proceeding without limit): %s", e)

    # Deduplicate by normalized URL (handles www, trailing slash, http/https)
    seen_urls: set[str] = set()
    deduped_posts: list[NormalizedPost] = []
    for post in posts:
        norm = normalize_url(post.url)
        if norm not in seen_urls:
            seen_urls.add(norm)
            post.url = norm  # Store the normalized URL
            deduped_posts.append(post)

    if len(deduped_posts) < len(posts):
        logger.info(
            "URL normalization deduped %d → %d posts",
            len(posts), len(deduped_posts),
        )

    # ── Pre-process: strip site names from titles, clean meta, filter nav ──
    for post in deduped_posts:
        post.title = _strip_site_name_from_title(post.title)
        post.meta_description = _strip_html_from_meta(post.meta_description)

    # Build link/heading maps for site-wide filtering
    links_map = {p.url: p.internal_links for p in deduped_posts}
    headings_map = {p.url: p.headings for p in deduped_posts}

    filtered_links = filter_nav_links(links_map)
    filtered_headings = filter_sitewide_headings(headings_map)

    for post in deduped_posts:
        post.internal_links = filtered_links.get(post.url, post.internal_links)
        post.headings = filtered_headings.get(post.url, post.headings)

    # ── Persist posts ──
    # Upsert each post individually (need RETURNING id for link mapping).
    url_to_id: dict[str, str] = {}
    for post in deduped_posts:
        try:
            headings_json = json.dumps(post.headings) if post.headings else None
            eeat_json = json.dumps(post.eeat_signals) if post.eeat_signals else "{}"

            row = await db.fetchrow(
                """
                INSERT INTO posts (
                    site_id, url, slug, title, body_text, body_html,
                    publish_date, modified_date, content_hash,
                    cms_categories, cms_tags, word_count,
                    headings, meta_description, http_status, language, page_type,
                    eeat_metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                ON CONFLICT (site_id, url) DO UPDATE SET
                    title = EXCLUDED.title,
                    body_text = EXCLUDED.body_text,
                    body_html = EXCLUDED.body_html,
                    modified_date = EXCLUDED.modified_date,
                    content_hash = EXCLUDED.content_hash,
                    cms_categories = EXCLUDED.cms_categories,
                    cms_tags = EXCLUDED.cms_tags,
                    word_count = EXCLUDED.word_count,
                    headings = EXCLUDED.headings,
                    meta_description = EXCLUDED.meta_description,
                    http_status = EXCLUDED.http_status,
                    language = EXCLUDED.language,
                    page_type = EXCLUDED.page_type,
                    eeat_metadata = EXCLUDED.eeat_metadata,
                    updated_at = NOW()
                RETURNING id
                """,
                site_id, post.url, post.slug, post.title,
                post.body_text, post.body_html,
                post.publish_date, post.modified_date,
                post.content_hash,
                post.cms_categories, post.cms_tags,
                post.word_count,
                headings_json, post.meta_description, post.http_status,
                post.language, post.page_type, eeat_json,
            )
            url_to_id[post.url] = row["id"]
            saved += 1

        except Exception as e:
            logger.error("Failed to save post %s: %s", post.url, e)
            continue

    # ── Batch internal links ──
    # Delete all existing internal links for this site's posts in one query,
    # then bulk-insert all new links. This is O(2) queries instead of O(2N).
    if url_to_id:
        post_ids = list(url_to_id.values())
        await db.execute(
            "DELETE FROM internal_links WHERE source_post_id = ANY($1::uuid[])",
            post_ids,
        )

        all_link_records: list[tuple] = []
        for post in deduped_posts:
            post_id = url_to_id.get(post.url)
            if not post_id or not post.internal_links:
                continue
            for link in post.internal_links:
                all_link_records.append(
                    (site_id, post_id, normalize_url(link.target_url), link.anchor_text)
                )

        if all_link_records:
            await db.executemany(
                """
                INSERT INTO internal_links (site_id, source_post_id, target_url, anchor_text)
                VALUES ($1, $2, $3, $4)
                """,
                all_link_records,
            )

    # Resolve internal link target_post_ids
    await _resolve_link_targets(db, site_id)

    logger.info("Saved %d/%d posts for site %s", saved, len(posts), site_id)
    return saved


async def _resolve_link_targets(db: asyncpg.Connection, site_id: UUID) -> None:
    """Match internal_links.target_url to posts.url and set target_post_id.

    Both target_url and post.url are already run through normalize_url()
    before storage (www stripped, trailing slashes removed, query params cleaned,
    scheme normalized to https). So a single exact-match pass is sufficient.

    Links that remain with target_post_id = NULL point to non-content URLs
    (login pages, image galleries, external-looking internal pages) that
    didn't survive the crawl's content gates (50-char minimum + 100-word minimum).
    """
    await db.execute(
        """
        UPDATE internal_links il
        SET target_post_id = p.id
        FROM posts p
        WHERE il.site_id = $1
          AND p.site_id = $1
          AND il.target_url = p.url
          AND il.target_post_id IS NULL
        """,
        site_id,
    )
