"""Content normalization layer.

Both WordPress and sitemap ingestion paths produce NormalizedPost objects,
which are then stored uniformly in the database.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

import asyncpg

from app.utils.url_normalize import normalize_url

logger = logging.getLogger(__name__)


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
