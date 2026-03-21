"""New content checker — detect cannibalization and cluster fit for newly crawled posts.

After a weekly recrawl detects new posts, this service checks:
1. Does the new post cannibalize any existing content? (embedding similarity)
2. Which cluster does it belong to?
3. Does it link to relevant existing posts?

Results are stored as position_alerts with alert_type='new_post_detected'.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class NewContentChecker:
    """Check newly crawled posts for cannibalization and cluster fit."""

    SIMILARITY_THRESHOLD = 0.3  # cosine distance threshold for cannibalization risk

    async def check_new_posts(
        self,
        db: asyncpg.Connection,
        site_id: UUID,
        new_post_ids: list[UUID],
    ) -> int:
        """Check a batch of newly detected posts.

        Returns the number of alerts generated.
        """
        alerts_created = 0
        now = datetime.now(timezone.utc)

        for post_id in new_post_ids:
            post = await db.fetchrow(
                "SELECT id, title, url FROM posts WHERE id = $1",
                post_id,
            )
            if not post:
                continue

            # Check embedding similarity against existing posts
            similar = await db.fetch(
                """
                SELECT p.id, p.title, p.url,
                       (pe1.embedding <=> pe2.embedding) AS distance
                FROM post_embeddings pe1
                JOIN post_embeddings pe2 ON pe2.post_id != pe1.post_id
                JOIN posts p ON p.id = pe2.post_id
                WHERE pe1.post_id = $1
                  AND p.site_id = $2
                  AND p.id != $1
                  AND (pe1.embedding <=> pe2.embedding) < $3
                ORDER BY distance ASC
                LIMIT 5
                """,
                post_id,
                site_id,
                self.SIMILARITY_THRESHOLD,
            )

            # Check which cluster it was assigned to
            cluster = await db.fetchrow(
                """
                SELECT c.id, c.label, c.ecosystem_state
                FROM post_clusters pc
                JOIN clusters c ON c.id = pc.cluster_id
                WHERE pc.post_id = $1
                """,
                post_id,
            )

            # Check internal links from this post
            outbound_links = await db.fetchval(
                "SELECT COUNT(*) FROM internal_links WHERE source_post_id = $1",
                post_id,
            ) or 0

            inbound_links = await db.fetchval(
                "SELECT COUNT(*) FROM internal_links WHERE target_post_id = $1",
                post_id,
            ) or 0

            has_cannibalization_risk = len(similar) > 0
            similar_posts = [
                {
                    "title": s["title"],
                    "url": s["url"],
                    "distance": round(float(s["distance"]), 3),
                }
                for s in similar
            ]

            details = {
                "cannibalization_risk": has_cannibalization_risk,
                "similar_posts": similar_posts,
                "cluster_label": cluster["label"] if cluster else None,
                "cluster_state": cluster["ecosystem_state"] if cluster else None,
                "outbound_links": outbound_links,
                "inbound_links": inbound_links,
            }

            await db.execute(
                """
                INSERT INTO position_alerts
                    (site_id, post_id, alert_type, details, detected_at)
                VALUES ($1, $2, 'new_post_detected', $3, $4)
                """,
                site_id,
                post_id,
                details,
                now,
            )
            alerts_created += 1

        logger.info(
            "New content checker for site %s: %d alerts from %d new posts",
            site_id,
            alerts_created,
            len(new_post_ids),
        )
        return alerts_created
