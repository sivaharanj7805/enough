"""Ecosystem Voice — Generate Claude-powered narrative summaries per cluster."""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

import asyncpg

from app.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


# Prompt templates per ecosystem state
NARRATIVE_PROMPTS: dict[str, str] = {
    "forest": (
        "Describe a thriving, old-growth forest region. The pillar post "
        "'{pillar_title}' has stood strong for {age} months. {supporter_count} "
        "supporting posts grow in its shade. Use nature metaphors. 2-3 sentences."
    ),
    "swamp": (
        "Describe a choking swamp. {post_count} posts fight for the same "
        "sunlight on '{topic}'. The best post is being strangled by its siblings. "
        "Use urgent, visceral nature metaphors. 2-3 sentences."
    ),
    "desert": (
        "Describe a barren desert. Posts on '{topic}' haven't been touched "
        "since {last_update}. The soil is still good but nothing grows. "
        "Use melancholy nature metaphors. 2-3 sentences."
    ),
    "seedbed": (
        "Describe fresh soil with new seedlings. Something was just planted "
        "on '{topic}'. It needs time and space to grow. Hopeful tone. 2-3 sentences."
    ),
    "meadow": (
        "Describe a quiet meadow. Content on '{topic}' is modest but stable. "
        "Room to grow or decline. Peaceful tone. 2-3 sentences."
    ),
}


class EcosystemVoice:
    """Generate ecosystem-metaphor narratives for content clusters."""

    def __init__(self) -> None:
        self.rate_limiter = RateLimiter(requests_per_second=3)

    async def generate_for_cluster(self, db: asyncpg.Connection, cluster_id: UUID) -> str:
        """Generate a narrative for a single cluster and store it."""
        from anthropic import AsyncAnthropic

        # Fetch cluster info
        cluster = await db.fetchrow(
            "SELECT id, label, ecosystem_state, post_count FROM clusters WHERE id = $1",
            cluster_id,
        )
        if not cluster:
            raise ValueError(f"Cluster {cluster_id} not found")

        state = cluster["ecosystem_state"] or "meadow"
        topic = cluster["label"] or "this topic"
        post_count = cluster["post_count"] or 0

        # Fetch additional context based on state
        pillar_title = ""
        age_months = 0
        supporter_count = 0
        last_update = "months ago"

        if state == "forest":
            pillar = await db.fetchrow(
                """
                SELECT p.title, p.publish_date
                FROM post_clusters pc
                JOIN posts p ON p.id = pc.post_id
                LEFT JOIN post_health_scores ph ON ph.post_id = p.id
                WHERE pc.cluster_id = $1 AND ph.role = 'pillar'
                ORDER BY ph.composite_score DESC NULLS LAST
                LIMIT 1
                """,
                cluster_id,
            )
            if pillar:
                pillar_title = pillar["title"] or topic
                if pillar["publish_date"]:
                    pub_date = pillar["publish_date"]
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                    delta = datetime.now(timezone.utc) - pub_date
                    age_months = max(1, delta.days // 30)

            supporter_count = await db.fetchval(
                """
                SELECT COUNT(*)
                FROM post_clusters pc
                JOIN post_health_scores ph ON ph.post_id = pc.post_id
                WHERE pc.cluster_id = $1 AND ph.role = 'supporter'
                """,
                cluster_id,
            ) or 0

        elif state in ("desert", "swamp", "seedbed", "meadow"):
            last_post = await db.fetchrow(
                """
                SELECT MAX(p.modified_date) AS last_mod
                FROM post_clusters pc
                JOIN posts p ON p.id = pc.post_id
                WHERE pc.cluster_id = $1
                """,
                cluster_id,
            )
            if last_post and last_post["last_mod"]:
                last_update = last_post["last_mod"].strftime("%B %Y")

        # Build prompt
        template = NARRATIVE_PROMPTS.get(state, NARRATIVE_PROMPTS["meadow"])
        prompt = template.format(
            pillar_title=pillar_title,
            age=age_months,
            supporter_count=supporter_count,
            post_count=post_count,
            topic=topic,
            last_update=last_update,
        )

        # Rate limit + call Claude
        await self.rate_limiter.wait()
        client = AsyncAnthropic()
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        narrative = response.content[0].text

        # Store/upsert narrative
        await db.execute(
            """
            INSERT INTO cluster_narratives (cluster_id, narrative_text, generated_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (cluster_id) DO UPDATE SET
                narrative_text = EXCLUDED.narrative_text,
                generated_at = EXCLUDED.generated_at
            """,
            cluster_id,
            narrative,
            datetime.now(timezone.utc),
        )

        logger.info("Generated narrative for cluster %s (state=%s)", cluster_id, state)
        return narrative

    async def generate_for_site(self, db: asyncpg.Connection, site_id: UUID) -> int:
        """Generate narratives for all clusters in a site. Returns count."""
        clusters = await db.fetch(
            "SELECT id FROM clusters WHERE site_id = $1", site_id
        )

        count = 0
        for row in clusters:
            try:
                await self.generate_for_cluster(db, row["id"])
                count += 1
            except Exception as e:
                logger.error(
                    "Failed to generate narrative for cluster %s: %s", row["id"], e
                )

        logger.info("Generated %d narratives for site %s", count, site_id)
        return count

    async def get_narrative(
        self, db: asyncpg.Connection, cluster_id: UUID
    ) -> dict | None:
        """Fetch stored narrative for a cluster."""
        row = await db.fetchrow(
            """
            SELECT cluster_id, narrative_text, generated_at
            FROM cluster_narratives
            WHERE cluster_id = $1
            """,
            cluster_id,
        )
        if not row:
            return None
        return dict(row)
