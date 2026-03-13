"""Competitor analysis — crawl, embed, and compare competitor content.

Crawls competitor sitemaps, embeds their content, and compares
topic coverage with yours. All free except OpenAI embedding costs
(~$0.01 per 1000 posts).

Capabilities:
1. Add/manage competitor sites
2. Crawl competitor sitemaps (reuses sitemap.py crawler)
3. Embed competitor content (text-embedding-3-small)
4. Topic coverage comparison (what do they cover that you don't?)
5. Content gap detection (competitor has 8 posts on X, you have 1)
6. Head-to-head analysis (shared keywords, who has better content?)
7. Competitive alerts (new competitor content in your clusters)
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID

import asyncpg
from openai import AsyncOpenAI

from app.config import get_settings
from app.services.sitemap import SitemapCrawler
from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Limits
MAX_COMPETITOR_POSTS = 200  # Max posts to crawl per competitor
SIMILARITY_THRESHOLD = 0.35  # For text-embedding-3-small topic matching


class CompetitorAnalyzer:
    """Crawl and analyze competitor content."""

    def __init__(self) -> None:
        settings = get_settings()
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def add_competitor(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        competitor_domain: str,
        name: str | None = None,
    ) -> UUID:
        """Add a competitor site to track.

        Returns the competitor_site_id.
        """
        # Normalize domain
        domain = competitor_domain.strip().lower()
        if domain.startswith("http"):
            domain = urlparse(domain).netloc
        domain = domain.replace("www.", "")

        # Auto-detect sitemap URL
        sitemap_url = f"https://{domain}/sitemap.xml"

        comp_id = await db.fetchval(
            """
            INSERT INTO competitor_sites (site_id, domain, name, sitemap_url)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (site_id, domain) DO UPDATE SET
                name = COALESCE($3, competitor_sites.name),
                sitemap_url = $4
            RETURNING id
            """,
            site_id, domain, name or domain, sitemap_url,
        )

        logger.info("Added competitor %s for site %s", domain, site_id)
        return comp_id

    async def crawl_competitor(
        self,
        db: asyncpg.Connection,
        competitor_site_id: UUID,
    ) -> int:
        """Crawl a competitor's sitemap and extract content.

        Returns number of posts crawled.
        """
        comp = await db.fetchrow(
            "SELECT * FROM competitor_sites WHERE id = $1", competitor_site_id,
        )
        if not comp:
            return 0

        site_id = comp["site_id"]
        domain = comp["domain"]

        await db.execute(
            "UPDATE competitor_sites SET status = 'crawling' WHERE id = $1",
            competitor_site_id,
        )

        try:
            # Use our sitemap crawler
            crawler = SitemapCrawler()
            pages = await crawler.crawl_sitemap(
                f"https://{domain}/sitemap.xml",
                max_pages=MAX_COMPETITOR_POSTS,
            )

            crawled = 0
            for page in pages:
                if not page.get("url"):
                    continue

                content_hash = hashlib.md5(
                    (page.get("body_text", "") or "").encode(),
                ).hexdigest()

                # Extract headings as JSON
                headings = page.get("headings", [])
                if isinstance(headings, list):
                    headings_json = json.dumps(headings)
                else:
                    headings_json = "[]"

                await db.execute(
                    """
                    INSERT INTO competitor_posts
                        (competitor_site_id, site_id, url, title,
                         meta_description, word_count, headings,
                         publish_date, body_text, content_hash)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10)
                    ON CONFLICT (competitor_site_id, url) DO UPDATE SET
                        title = $4, meta_description = $5,
                        word_count = $6, headings = $7::jsonb,
                        body_text = $9, content_hash = $10,
                        crawled_at = NOW()
                    """,
                    competitor_site_id, site_id, page["url"],
                    page.get("title"), page.get("meta_description"),
                    page.get("word_count", 0), headings_json,
                    page.get("publish_date"),
                    page.get("body_text"), content_hash,
                )
                crawled += 1

            await db.execute(
                """
                UPDATE competitor_sites
                SET status = 'crawled', last_crawled_at = NOW(),
                    post_count = $1, error_message = NULL
                WHERE id = $2
                """,
                crawled, competitor_site_id,
            )

            logger.info("Crawled %d posts from %s", crawled, domain)
            return crawled

        except Exception as e:
            await db.execute(
                """
                UPDATE competitor_sites
                SET status = 'error', error_message = $1
                WHERE id = $2
                """,
                str(e)[:500], competitor_site_id,
            )
            logger.error("Failed to crawl %s: %s", domain, e)
            return 0

    async def embed_competitor_content(
        self,
        db: asyncpg.Connection,
        competitor_site_id: UUID,
    ) -> int:
        """Generate embeddings for competitor posts.

        Returns number of posts embedded.
        """
        posts = await db.fetch(
            """
            SELECT cp.id, cp.title, cp.body_text
            FROM competitor_posts cp
            LEFT JOIN competitor_embeddings ce ON ce.competitor_post_id = cp.id
            WHERE cp.competitor_site_id = $1
              AND ce.id IS NULL
              AND cp.body_text IS NOT NULL
              AND LENGTH(cp.body_text) > 100
            LIMIT $2
            """,
            competitor_site_id, MAX_COMPETITOR_POSTS,
        )

        if not posts:
            return 0

        embedded = 0
        batch_size = 20  # OpenAI batch limit

        for i in range(0, len(posts), batch_size):
            batch = posts[i:i + batch_size]
            texts = []
            for p in batch:
                # Use title-weighted text for better topic matching
                title = p["title"] or ""
                body = (p["body_text"] or "")[:3000]
                texts.append(f"{title}. {title}. {title}. {body}")

            await self.rate_limiter.wait()
            try:
                response = await self.openai.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )

                for j, embedding_data in enumerate(response.data):
                    post = batch[j]
                    embedding = embedding_data.embedding

                    await db.execute(
                        """
                        INSERT INTO competitor_embeddings
                            (competitor_post_id, embedding)
                        VALUES ($1, $2)
                        ON CONFLICT (competitor_post_id) DO UPDATE SET
                            embedding = $2, created_at = NOW()
                        """,
                        post["id"], str(embedding),
                    )
                    embedded += 1
            except Exception as e:
                logger.error("Embedding batch failed: %s", e)

        logger.info("Embedded %d competitor posts", embedded)
        return embedded

    async def analyze_competition(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> dict[str, int]:
        """Run full competitive analysis for a site.

        Compares all competitor content with our content to find:
        - Topic gaps (they cover it, we don't)
        - Content advantages (we're better)
        - Content disadvantages (they're better)
        - New threats (recent competitor content)

        Returns counts by insight type.
        """
        logger.info("Running competitive analysis for site %s", site_id)

        # Clear old insights
        await db.execute(
            "DELETE FROM competitive_insights WHERE site_id = $1", site_id,
        )

        competitors = await db.fetch(
            "SELECT id, domain, name FROM competitor_sites WHERE site_id = $1 AND status = 'crawled'",
            site_id,
        )

        if not competitors:
            logger.info("No crawled competitors for site %s", site_id)
            return {}

        counts: dict[str, int] = {}

        for comp in competitors:
            result = await self._analyze_single_competitor(
                db, site_id, comp["id"], comp["domain"], comp["name"],
            )
            for k, v in result.items():
                counts[k] = counts.get(k, 0) + v

        logger.info("Competitive analysis complete: %s", counts)
        return counts

    async def _analyze_single_competitor(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        competitor_id: UUID,
        competitor_domain: str,
        competitor_name: str,
    ) -> dict[str, int]:
        """Analyze one competitor against our content."""
        counts = {"topic_gap": 0, "content_advantage": 0, "content_disadvantage": 0, "new_content": 0}

        # ── Topic Gap Detection ──
        # Find competitor posts that don't match any of our clusters well
        our_clusters = await db.fetch(
            """
            SELECT c.id, c.label, c.post_count,
                   c.topical_authority_score
            FROM clusters c
            WHERE c.site_id = $1
            """,
            site_id,
        )

        # For each competitor post, find closest match in our content
        comp_posts = await db.fetch(
            """
            SELECT cp.id, cp.title, cp.word_count, cp.publish_date,
                   cp.meta_description
            FROM competitor_posts cp
            WHERE cp.competitor_site_id = $1
            ORDER BY cp.publish_date DESC NULLS LAST
            """,
            competitor_id,
        )

        for cp in comp_posts:
            # Find closest post in our site via embedding
            closest = await db.fetchrow(
                """
                SELECT p.id, p.title,
                       1 - (pe.embedding <=> ce.embedding) AS similarity
                FROM competitor_embeddings ce
                CROSS JOIN LATERAL (
                    SELECT pe2.post_id, pe2.embedding
                    FROM post_embeddings pe2
                    JOIN posts p2 ON p2.id = pe2.post_id
                    WHERE p2.site_id = $2
                    ORDER BY pe2.embedding <=> ce.embedding
                    LIMIT 1
                ) pe
                JOIN posts p ON p.id = pe.post_id
                WHERE ce.competitor_post_id = $1
                """,
                cp["id"], site_id,
            )

            if not closest:
                continue

            similarity = float(closest["similarity"]) if closest["similarity"] else 0

            # Check if this is a topic gap (low similarity = they cover something we don't)
            if similarity < SIMILARITY_THRESHOLD:
                await db.execute(
                    """
                    INSERT INTO competitive_insights
                        (site_id, competitor_site_id, insight_type,
                         competitor_post_id, title, details, priority)
                    VALUES ($1, $2, 'topic_gap', $3, $4, $5, $6)
                    """,
                    site_id, competitor_id, cp["id"],
                    f"{competitor_name} covers: {cp['title']}",
                    json.dumps({
                        "competitor_title": cp["title"],
                        "competitor_url": None,
                        "closest_match": closest["title"],
                        "similarity": round(similarity, 3),
                        "competitor_word_count": cp["word_count"],
                    }),
                    "high" if (cp["word_count"] or 0) > 1500 else "medium",
                )
                counts["topic_gap"] += 1

            # Check for head-to-head (high similarity = same topic)
            elif similarity > 0.45:
                # Compare quality signals
                our_post = await db.fetchrow(
                    """
                    SELECT p.word_count, ph.composite_score
                    FROM posts p
                    LEFT JOIN post_health_scores ph ON ph.post_id = p.id
                    WHERE p.id = $1
                    """,
                    closest["id"],
                )

                our_wc = our_post["word_count"] or 0 if our_post else 0
                our_health = our_post["composite_score"] or 0 if our_post else 0
                comp_wc = cp["word_count"] or 0

                if comp_wc > our_wc * 1.5:
                    # Competitor has significantly more content
                    await db.execute(
                        """
                        INSERT INTO competitive_insights
                            (site_id, competitor_site_id, insight_type,
                             our_post_id, competitor_post_id,
                             title, details, priority)
                        VALUES ($1, $2, 'content_disadvantage', $3, $4, $5, $6, $7)
                        """,
                        site_id, competitor_id, closest["id"], cp["id"],
                        f"Competitor outguns you on: {closest['title']}",
                        json.dumps({
                            "our_title": closest["title"],
                            "our_word_count": our_wc,
                            "our_health_score": round(our_health, 1),
                            "competitor_title": cp["title"],
                            "competitor_word_count": comp_wc,
                            "word_count_ratio": round(comp_wc / max(our_wc, 1), 1),
                            "similarity": round(similarity, 3),
                        }),
                        "high",
                    )
                    counts["content_disadvantage"] += 1
                elif our_wc > comp_wc * 1.3 and our_health > 60:
                    # We have the advantage
                    await db.execute(
                        """
                        INSERT INTO competitive_insights
                            (site_id, competitor_site_id, insight_type,
                             our_post_id, competitor_post_id,
                             title, details, priority)
                        VALUES ($1, $2, 'content_advantage', $3, $4, $5, $6, $7)
                        """,
                        site_id, competitor_id, closest["id"], cp["id"],
                        f"You're winning on: {closest['title']}",
                        json.dumps({
                            "our_title": closest["title"],
                            "our_word_count": our_wc,
                            "our_health_score": round(our_health, 1),
                            "competitor_title": cp["title"],
                            "competitor_word_count": comp_wc,
                            "similarity": round(similarity, 3),
                        }),
                        "low",
                    )
                    counts["content_advantage"] += 1

            # Check for new content threats (published in last 30 days)
            now = datetime.now(timezone.utc)
            if cp["publish_date"] and cp["publish_date"] > now - timedelta(days=30):
                # Find which of our clusters this targets
                target_cluster = None
                for cluster in our_clusters:
                    cluster_posts = await db.fetch(
                        "SELECT post_id FROM post_clusters WHERE cluster_id = $1",
                        cluster["id"],
                    )
                    for cp_row in cluster_posts:
                        match = await db.fetchrow(
                            """
                            SELECT 1 - (pe.embedding <=> ce.embedding) AS sim
                            FROM post_embeddings pe, competitor_embeddings ce
                            WHERE pe.post_id = $1 AND ce.competitor_post_id = $2
                            """,
                            cp_row["post_id"], cp["id"],
                        )
                        if match and float(match["sim"]) > 0.40:
                            target_cluster = cluster
                            break
                    if target_cluster:
                        break

                if target_cluster:
                    await db.execute(
                        """
                        INSERT INTO competitive_insights
                            (site_id, competitor_site_id, insight_type,
                             cluster_id, competitor_post_id,
                             title, details, priority)
                        VALUES ($1, $2, 'new_content', $3, $4, $5, $6, $7)
                        """,
                        site_id, competitor_id,
                        target_cluster["id"], cp["id"],
                        f"🚨 {competitor_name} just published in your '{target_cluster['label']}' cluster",
                        json.dumps({
                            "competitor_title": cp["title"],
                            "competitor_word_count": cp["word_count"],
                            "target_cluster": target_cluster["label"],
                            "cluster_authority": round(
                                target_cluster["topical_authority_score"] or 0, 1,
                            ),
                            "published": cp["publish_date"].isoformat() if cp["publish_date"] else None,
                        }),
                        "critical",
                    )
                    counts["new_content"] += 1

        return counts

    async def get_coverage_comparison(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
    ) -> dict:
        """Get a topic coverage comparison across all competitors.

        Returns a summary of which topics each site covers.
        """
        our_clusters = await db.fetch(
            """
            SELECT c.id, c.label, c.post_count,
                   c.topical_authority_score
            FROM clusters c
            WHERE c.site_id = $1
            ORDER BY c.topical_authority_score DESC NULLS LAST
            """,
            site_id,
        )

        competitors = await db.fetch(
            "SELECT id, domain, name, post_count FROM competitor_sites WHERE site_id = $1",
            site_id,
        )

        insights_summary = await db.fetch(
            """
            SELECT cs.name AS competitor,
                   ci.insight_type,
                   COUNT(*) AS count
            FROM competitive_insights ci
            JOIN competitor_sites cs ON cs.id = ci.competitor_site_id
            WHERE ci.site_id = $1
            GROUP BY cs.name, ci.insight_type
            ORDER BY cs.name
            """,
            site_id,
        )

        return {
            "our_clusters": [dict(c) for c in our_clusters],
            "competitors": [dict(c) for c in competitors],
            "insights": [dict(i) for i in insights_summary],
        }
