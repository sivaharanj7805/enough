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
        # If last segment is short (≤4 words), it's likely a site name
        if len(last.split()) <= 4:
            return _TITLE_SEPARATORS.split(title, maxsplit=len(parts) - 2)[0].strip()
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
    threshold: float = 0.8,
) -> dict[str, list[dict[str, str]]]:
    """Remove headings that appear on almost every page (site header/footer).

    Args:
        all_posts_headings: mapping of post_url → list of heading dicts
        threshold: if a heading text appears in ≥ this fraction of posts, remove it

    Returns:
        Filtered mapping with sitewide headings removed.
    """
    if not all_posts_headings:
        return all_posts_headings

    total_posts = len(all_posts_headings)
    if total_posts < 3:
        return all_posts_headings

    # Count heading occurrences
    heading_counts: Counter[str] = Counter()
    for headings in all_posts_headings.values():
        seen = set()
        for h in headings:
            text = h.get("text", "").strip().lower()
            if text and text not in seen:
                heading_counts[text] += 1
                seen.add(text)

    # Only filter H1-level sitewide headings (site name, nav items)
    # H2+ headings that repeat are likely legitimate section patterns
    h1_counts: Counter[str] = Counter()
    for headings in all_posts_headings.values():
        seen = set()
        for h in headings:
            text = h.get("text", "").strip().lower()
            level = str(h.get("level", "")).replace("h", "")
            if text and text not in seen and level == "1":
                h1_counts[text] += 1
                seen.add(text)

    sitewide: set[str] = set()
    for text, count in h1_counts.items():
        if count / total_posts >= threshold:
            sitewide.add(text)

    if sitewide:
        logger.info(
            "Detected %d sitewide headings (in ≥%.0f%% of posts): %s",
            len(sitewide), threshold * 100,
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
    word_count: int = 0
    content_hash: str = ""
    headings: list[dict[str, str]] = field(default_factory=list)
    meta_description: str | None = None
    http_status: int | None = None

    def __post_init__(self):
        if not self.word_count and self.body_text:
            self.word_count = len(self.body_text.split())
        if not self.content_hash and self.body_text:
            self.content_hash = hashlib.sha256(
                self.body_text.encode("utf-8")
            ).hexdigest()


def compute_content_hash(text: str) -> str:
    """SHA256 hash of content for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def save_normalized_posts(
    db: asyncpg.Connection,
    site_id: UUID,
    posts: list[NormalizedPost],
) -> int:
    """Upsert normalized posts and their internal links into the database.

    Returns the number of posts saved.
    """
    saved = 0

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

    # ── Persist ──
    for post in deduped_posts:
        try:
            # Serialize headings to JSON
            headings_json = json.dumps(post.headings) if post.headings else None

            # Upsert the post
            row = await db.fetchrow(
                """
                INSERT INTO posts (
                    site_id, url, slug, title, body_text, body_html,
                    publish_date, modified_date, content_hash,
                    cms_categories, cms_tags, word_count,
                    headings, meta_description, http_status
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
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
            )

            post_id = row["id"]

            # Clear existing internal links for this post and re-insert
            await db.execute(
                "DELETE FROM internal_links WHERE source_post_id = $1",
                post_id,
            )

            if post.internal_links:
                link_records = [
                    (site_id, post_id, normalize_url(link.target_url), link.anchor_text)
                    for link in post.internal_links
                ]
                await db.executemany(
                    """
                    INSERT INTO internal_links (site_id, source_post_id, target_url, anchor_text)
                    VALUES ($1, $2, $3, $4)
                    """,
                    link_records,
                )

            saved += 1

        except Exception as e:
            logger.error("Failed to save post %s: %s", post.url, e)
            continue

    # Resolve internal link target_post_ids
    await _resolve_link_targets(db, site_id)

    logger.info("Saved %d/%d posts for site %s", saved, len(posts), site_id)
    return saved


async def _resolve_link_targets(db: asyncpg.Connection, site_id: UUID) -> None:
    """Match internal_links.target_url to posts.url and set target_post_id."""
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
