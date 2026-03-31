"""Content Wrapped — Spotify Wrapped-style content review generator."""

import logging
from datetime import date, timedelta
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class ContentWrappedService:
    """Generate a 'Spotify Wrapped'-style content review for a site."""

    async def generate(self, db: asyncpg.Connection, site_id: UUID, period: str) -> dict:
        """Generate wrapped data for a given period (e.g. '2025-12' or '2025').

        Returns a dict of stats and narrative elements.
        """
        # Parse period to determine date range
        if len(period) == 7:
            # Monthly: "2025-12"
            year, month = int(period[:4]), int(period[5:7])
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
        elif len(period) == 4:
            # Yearly: "2025"
            year = int(period)
            start_date = date(year, 1, 1)
            end_date = date(year, 12, 31)
        else:
            start_date = date.today() - timedelta(days=30)
            end_date = date.today()

        # Total posts analyzed
        total_posts = await db.fetchval(
            "SELECT COUNT(*) FROM posts WHERE site_id = $1",
            site_id,
        ) or 0

        # Posts created in period
        posts_created = await db.fetchval(
            """SELECT COUNT(*) FROM posts
               WHERE site_id = $1
               AND created_at >= $2 AND created_at <= $3""",
            site_id, start_date, end_date,
        ) or 0

        # Health score journey — start and end
        health_start = await db.fetchval(
            """SELECT score FROM health_score_history
               WHERE site_id = $1 AND recorded_at >= $2
               ORDER BY recorded_at ASC LIMIT 1""",
            site_id, start_date,
        )
        health_end = await db.fetchval(
            """SELECT score FROM health_score_history
               WHERE site_id = $1 AND recorded_at <= $2
               ORDER BY recorded_at DESC LIMIT 1""",
            site_id, end_date,
        )

        # Biggest improvement — post that gained most health
        biggest_improvement = await db.fetchrow(
            """SELECT p.title, p.url, ph.composite_score
               FROM post_health ph
               JOIN posts p ON p.id = ph.post_id
               WHERE p.site_id = $1
               ORDER BY ph.composite_score DESC NULLS LAST
               LIMIT 1""",
            site_id,
        )

        # Worst offender — lowest scoring post
        worst_offender = await db.fetchrow(
            """SELECT p.title, p.url, ph.composite_score
               FROM post_health ph
               JOIN posts p ON p.id = ph.post_id
               WHERE p.site_id = $1 AND ph.composite_score IS NOT NULL
               ORDER BY ph.composite_score ASC
               LIMIT 1""",
            site_id,
        )

        # Top cluster — highest health score
        top_cluster = await db.fetchrow(
            """SELECT label, health_score, post_count
               FROM clusters
               WHERE site_id = $1 AND health_score IS NOT NULL
               ORDER BY health_score DESC LIMIT 1""",
            site_id,
        )

        # Cluster stats
        cluster_count = await db.fetchval(
            "SELECT COUNT(*) FROM clusters WHERE site_id = $1",
            site_id,
        ) or 0

        # Ecosystem state counts
        ecosystem_states = await db.fetch(
            """SELECT ecosystem_state, COUNT(*) as cnt
               FROM clusters WHERE site_id = $1
               GROUP BY ecosystem_state""",
            site_id,
        )
        state_counts = {row["ecosystem_state"]: row["cnt"] for row in ecosystem_states if row["ecosystem_state"]}
        swamps_found = state_counts.get("swamp", 0)
        deserts_found = state_counts.get("desert", 0)

        # Cannibalization pairs
        cann_pairs = await db.fetchval(
            "SELECT COUNT(*) FROM cannibalization_pairs WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)",
            site_id,
        ) or 0

        # Total word count
        total_words = await db.fetchval(
            "SELECT COALESCE(SUM(word_count), 0) FROM posts WHERE site_id = $1",
            site_id,
        ) or 0

        # Generate ecosystem size narrative
        if total_posts >= 500:
            ecosystem_narrative = "Your content ecosystem grew into a vast forest"
        elif total_posts >= 200:
            ecosystem_narrative = "Your content ecosystem blossomed into a thriving woodland"
        elif total_posts >= 50:
            ecosystem_narrative = "Your content ecosystem developed into a growing garden"
        else:
            ecosystem_narrative = "Your content ecosystem sprouted from a seedbed"

        wrapped_data = {
            "period": period,
            "total_posts": total_posts,
            "posts_created": posts_created,
            "health_score_start": float(health_start) if health_start else None,
            "health_score_end": float(health_end) if health_end else None,
            "health_improvement": (
                round(float(health_end) - float(health_start), 1)
                if health_start and health_end
                else None
            ),
            "biggest_improvement": (
                {
                    "title": biggest_improvement["title"],
                    "url": biggest_improvement["url"],
                    "score": float(biggest_improvement["composite_score"]) if biggest_improvement["composite_score"] else 0,
                }
                if biggest_improvement
                else None
            ),
            "worst_offender": (
                {
                    "title": worst_offender["title"],
                    "url": worst_offender["url"],
                    "score": float(worst_offender["composite_score"]) if worst_offender["composite_score"] else 0,
                }
                if worst_offender
                else None
            ),
            "top_cluster": (
                {
                    "label": top_cluster["label"],
                    "health_score": float(top_cluster["health_score"]),
                    "post_count": top_cluster["post_count"],
                }
                if top_cluster
                else None
            ),
            "cluster_count": cluster_count,
            "swamps_found": swamps_found,
            "deserts_found": deserts_found,
            "cannibalization_pairs": cann_pairs,
            "total_words": total_words,
            "ecosystem_narrative": ecosystem_narrative,
            "slides": self._build_slides(
                total_posts=total_posts,
                posts_created=posts_created,
                health_start=float(health_start) if health_start else None,
                health_end=float(health_end) if health_end else None,
                top_cluster=top_cluster,
                biggest_improvement=biggest_improvement,
                worst_offender=worst_offender,
                total_words=total_words,
                cann_pairs=cann_pairs,
                ecosystem_narrative=ecosystem_narrative,
                period=period,
            ),
        }

        # Upsert into content_wrapped table
        await db.execute(
            """INSERT INTO content_wrapped (site_id, period, data)
               VALUES ($1, $2, $3::jsonb)
               ON CONFLICT (site_id, period) DO UPDATE SET data = $3::jsonb, created_at = NOW()""",
            site_id,
            period,
            __import__("json").dumps(wrapped_data),
        )

        return wrapped_data

    def _build_slides(
        self,
        total_posts: int,
        posts_created: int,
        health_start: float | None,
        health_end: float | None,
        top_cluster,
        biggest_improvement,
        worst_offender,
        total_words: int,
        cann_pairs: int,
        ecosystem_narrative: str,
        period: str,
    ) -> list[dict]:
        """Build the slide deck for the wrapped experience."""
        slides = []

        # Slide 1: Intro
        slides.append({
            "title": f"Your Content Wrapped — {period}",
            "subtitle": ecosystem_narrative,
            "stat": None,
            "color": "from-indigo-600 to-purple-700",
        })

        # Slide 2: Total posts
        slides.append({
            "title": "Posts Analyzed",
            "subtitle": "We analyzed every corner of your content ecosystem",
            "stat": str(total_posts),
            "stat_label": "total posts",
            "color": "from-blue-600 to-cyan-600",
        })

        # Slide 3: Words written
        if total_words > 0:
            books = total_words // 50000
            slides.append({
                "title": "Words in Your Ecosystem",
                "subtitle": f"That's roughly {books} novel{'s' if books != 1 else ''}!" if books > 0 else "Every word tells a story",
                "stat": f"{total_words:,}",
                "stat_label": "total words",
                "color": "from-emerald-600 to-teal-600",
            })

        # Slide 4: Health journey
        if health_start is not None and health_end is not None:
            delta = round(health_end - health_start, 1)
            direction = "climbed" if delta > 0 else "shifted" if delta == 0 else "dipped"
            slides.append({
                "title": "Health Score Journey",
                "subtitle": f"Your score {direction} from {health_start:.0f} to {health_end:.0f}",
                "stat": f"{'+' if delta > 0 else ''}{delta}",
                "stat_label": "point change",
                "color": "from-green-600 to-emerald-600" if delta > 0 else "from-orange-600 to-red-600",
            })

        # Slide 5: Top cluster
        if top_cluster:
            slides.append({
                "title": "Your Strongest Topic",
                "subtitle": f'"{top_cluster["label"]}" led the way with {top_cluster["post_count"]} posts',
                "stat": f'{top_cluster["health_score"]:.0f}',
                "stat_label": "health score",
                "color": "from-violet-600 to-purple-600",
            })

        # Slide 6: Best post
        if biggest_improvement:
            slides.append({
                "title": "Star Performer",
                "subtitle": biggest_improvement["title"],
                "stat": f'{biggest_improvement["composite_score"]:.0f}' if biggest_improvement["composite_score"] else "N/A",
                "stat_label": "health score",
                "color": "from-yellow-500 to-orange-500",
            })

        # Slide 7: Worst offender
        if worst_offender:
            slides.append({
                "title": "Needs Love",
                "subtitle": worst_offender["title"],
                "stat": f'{worst_offender["composite_score"]:.0f}' if worst_offender["composite_score"] else "N/A",
                "stat_label": "health score",
                "color": "from-red-600 to-pink-600",
            })

        # Slide 8: Cannibalization
        if cann_pairs > 0:
            slides.append({
                "title": "Cannibalization Alert",
                "subtitle": f"We found {cann_pairs} pairs of posts competing with each other",
                "stat": str(cann_pairs),
                "stat_label": "competing pairs",
                "color": "from-red-700 to-orange-600",
            })

        # Slide 9: Posts created
        if posts_created > 0:
            slides.append({
                "title": "Fresh Content",
                "subtitle": f"You published {posts_created} new pieces this period",
                "stat": str(posts_created),
                "stat_label": "new posts",
                "color": "from-cyan-600 to-blue-600",
            })

        # Slide 10: Outro
        slides.append({
            "title": "Keep Growing",
            "subtitle": "Your content ecosystem is alive. Let's make it thrive.",
            "stat": None,
            "color": "from-indigo-600 to-violet-700",
        })

        return slides
