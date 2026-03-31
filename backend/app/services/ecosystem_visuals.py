"""Ecosystem visuals service — computes rivers, grass, weather, animals, and terrain features."""

import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


def _grass_state(days_old: float) -> str:
    """Assign grass state based on average content age in days."""
    if days_old < 90:
        return "fresh"
    elif days_old < 365:
        return "maintained"
    elif days_old < 730:
        return "overgrown"
    else:
        return "dead"


def _weather_state(recent: int, previous_monthly: float) -> tuple[str, float | None]:
    """Assign weather state based on traffic trend.

    Returns (state, change_percent).
    """
    if previous_monthly == 0 and recent == 0:
        return "fog", None
    if previous_monthly == 0:
        return "sunny", None

    change_pct = (recent - previous_monthly) / previous_monthly * 100
    if change_pct > 20:
        state = "sunny"
    elif change_pct > -5:
        state = "cloudy"
    elif change_pct > -25:
        state = "rain"
    else:
        state = "storm"
    return state, round(change_pct, 1)


def _river_width(total_links: int) -> float:
    """Compute river width from total link count (1-5 scale)."""
    return min(total_links / 3.0, 5.0)


class EcosystemVisualsService:
    """Computes all visual metadata for the living ecosystem landscape."""

    async def compute_visuals(self, db: asyncpg.Connection, site_id: UUID) -> dict:
        """Compute all ecosystem visual metadata for a site."""
        # Fetch clusters
        clusters = await db.fetch(
            """SELECT id, label, post_count, ecosystem_state FROM clusters
               WHERE site_id = $1
               AND id NOT IN (
                   SELECT parent_cluster_id FROM clusters
                   WHERE parent_cluster_id IS NOT NULL AND site_id = $1
               )""",
            site_id,
        )
        if not clusters:
            return {
                "clusters": [],
                "rivers": [],
                "grass": {},
                "weather": {},
                "animals": {},
                "water_quality_note": None,
                "terrain_features": {},
            }

        cluster_list = [dict(c) for c in clusters]

        # Compute cluster center positions from post 2D coordinates
        cluster_positions = await self._compute_cluster_positions(db, cluster_list)

        rivers = await self._compute_rivers(db, site_id, cluster_list)
        grass = await self._compute_grass(db, cluster_list)
        weather = await self._compute_weather(db, cluster_list)
        animals = await self._compute_animals(db, cluster_list)
        terrain_features = await self._compute_terrain_features(db, cluster_list)

        # Enhance rivers with water quality
        rivers = await self._compute_water_quality(db, rivers)

        return {
            "clusters": cluster_positions,
            "rivers": rivers,
            "grass": grass,
            "weather": weather,
            "animals": animals,
            "water_quality_note": "Water quality based on engagement metrics of connected clusters",
            "terrain_features": terrain_features,
        }

    async def _compute_cluster_positions(
        self, db: asyncpg.Connection, clusters: list[dict],
    ) -> list[dict]:
        """Compute cluster center positions from post 2D coordinates.

        Each cluster's center is the mean of its posts' x_pos/y_pos.
        Returns list of cluster dicts with id, label, x, y, post_count, ecosystem_state.
        """
        result = []
        for cluster in clusters:
            cid = cluster["id"]
            center = await db.fetchrow(
                """
                SELECT AVG(p.x_pos) AS cx, AVG(p.y_pos) AS cy
                FROM post_clusters pc
                JOIN posts p ON p.id = pc.post_id
                WHERE pc.cluster_id = $1 AND p.x_pos IS NOT NULL
                """,
                cid,
            )
            cx = float(center["cx"]) if center and center["cx"] is not None else 0.0
            cy = float(center["cy"]) if center and center["cy"] is not None else 0.0
            result.append({
                "id": str(cid),
                "label": cluster.get("label", ""),
                "x": cx,
                "y": cy,
                "post_count": cluster.get("post_count", 0),
                "ecosystem_state": cluster.get("ecosystem_state", "seedbed"),
            })
        return result

    async def _compute_rivers(
        self, db: asyncpg.Connection, site_id: UUID, clusters: list[dict]
    ) -> list[dict]:
        """Compute internal link flow between clusters."""
        rivers = []

        # Pre-fetch post IDs for each cluster
        cluster_posts: dict[str, list] = {}
        for cluster in clusters:
            cid = cluster["id"]
            rows = await db.fetch(
                "SELECT post_id FROM post_clusters WHERE cluster_id = $1", cid
            )
            cluster_posts[str(cid)] = [r["post_id"] for r in rows]

        # For each pair of clusters, count links
        for i, c1 in enumerate(clusters):
            for c2 in clusters[i + 1 :]:
                c1_ids = cluster_posts.get(str(c1["id"]), [])
                c2_ids = cluster_posts.get(str(c2["id"]), [])

                if not c1_ids or not c2_ids:
                    continue

                forward_links = await db.fetchval(
                    """
                    SELECT COUNT(*) FROM internal_links
                    WHERE source_post_id = ANY($1::uuid[]) AND target_post_id = ANY($2::uuid[])
                    """,
                    c1_ids,
                    c2_ids,
                )

                backward_links = await db.fetchval(
                    """
                    SELECT COUNT(*) FROM internal_links
                    WHERE source_post_id = ANY($1::uuid[]) AND target_post_id = ANY($2::uuid[])
                    """,
                    c2_ids,
                    c1_ids,
                )

                forward_links = forward_links or 0
                backward_links = backward_links or 0
                total = forward_links + backward_links

                if total > 0:
                    max_dir = max(forward_links, backward_links, 1)
                    min_dir = min(forward_links, backward_links)
                    rivers.append(
                        {
                            "from_cluster_id": str(c1["id"]),
                            "to_cluster_id": str(c2["id"]),
                            "forward_links": forward_links,
                            "backward_links": backward_links,
                            "total_links": total,
                            "bidirectional_ratio": round(min_dir / max_dir, 2),
                            "width": round(_river_width(total), 2),
                            "quality": "clear",
                        }
                    )

        return rivers

    async def _compute_grass(
        self, db: asyncpg.Connection, clusters: list[dict]
    ) -> dict[str, dict]:
        """Per-cluster freshness ground cover."""
        grass: dict[str, dict] = {}
        for cluster in clusters:
            cid = cluster["id"]

            row = await db.fetchrow(
                """
                SELECT
                    AVG(EXTRACT(EPOCH FROM (NOW() - COALESCE(p.modified_date, p.publish_date)))) AS avg_age,
                    MAX(EXTRACT(EPOCH FROM (NOW() - COALESCE(p.modified_date, p.publish_date)))) AS oldest_age,
                    MIN(EXTRACT(EPOCH FROM (NOW() - COALESCE(p.modified_date, p.publish_date)))) AS newest_age
                FROM posts p
                JOIN post_clusters pc ON pc.post_id = p.id
                WHERE pc.cluster_id = $1
                """,
                cid,
            )

            avg_age = (row["avg_age"] or 0) if row else 0
            days_old = avg_age / 86400

            oldest_days = None
            newest_days = None
            if row and row["oldest_age"] is not None:
                oldest_days = round(row["oldest_age"] / 86400)
            if row and row["newest_age"] is not None:
                newest_days = round(row["newest_age"] / 86400)

            grass[str(cid)] = {
                "state": _grass_state(days_old),
                "avg_days_old": round(days_old),
                "oldest_post_days": oldest_days,
                "newest_post_days": newest_days,
            }

        return grass

    async def _compute_weather(
        self, db: asyncpg.Connection, clusters: list[dict]
    ) -> dict[str, dict]:
        """Per-cluster weather based on traffic trends."""
        weather: dict[str, dict] = {}
        for cluster in clusters:
            cid = cluster["id"]

            recent = await db.fetchval(
                """
                SELECT COALESCE(SUM(gm.clicks), 0)
                FROM gsc_metrics gm
                JOIN post_clusters pc ON pc.post_id = gm.post_id
                WHERE pc.cluster_id = $1
                AND gm.date >= NOW() - INTERVAL '30 days'
                """,
                cid,
            )

            previous = await db.fetchval(
                """
                SELECT COALESCE(SUM(gm.clicks), 0)
                FROM gsc_metrics gm
                JOIN post_clusters pc ON pc.post_id = gm.post_id
                WHERE pc.cluster_id = $1
                AND gm.date >= NOW() - INTERVAL '90 days'
                AND gm.date < NOW() - INTERVAL '30 days'
                """,
                cid,
            )

            recent = recent or 0
            previous = previous or 0
            prev_monthly = previous / 2  # 60 days → monthly avg

            state, change_pct = _weather_state(recent, prev_monthly)

            weather[str(cid)] = {
                "state": state,
                "recent_traffic": recent,
                "previous_traffic": round(prev_monthly),
                "change_percent": change_pct,
            }

        return weather

    async def _compute_animals(
        self, db: asyncpg.Connection, clusters: list[dict]
    ) -> dict[str, list[dict]]:
        """Per-cluster animal population based on behavior metrics."""
        animals: dict[str, list[dict]] = {}

        for cluster in clusters:
            cid = cluster["id"]
            cluster_animals: list[dict] = []

            # Birds = high impressions, low CTR
            avg_ctr = await db.fetchval(
                """
                SELECT AVG(gm.ctr) FROM gsc_metrics gm
                JOIN post_clusters pc ON pc.post_id = gm.post_id
                WHERE pc.cluster_id = $1
                """,
                cid,
            )

            avg_impressions = await db.fetchval(
                """
                SELECT AVG(gm.impressions) FROM gsc_metrics gm
                JOIN post_clusters pc ON pc.post_id = gm.post_id
                WHERE pc.cluster_id = $1
                """,
                cid,
            )

            if (
                avg_ctr is not None
                and avg_impressions is not None
                and avg_ctr < 0.02
                and avg_impressions > 500
            ):
                bird_count = min(int((0.02 - avg_ctr) * 200), 5)
                cluster_animals.append(
                    {
                        "type": "birds",
                        "count": max(bird_count, 1),
                        "meaning": f"High impressions ({avg_impressions:.0f}/mo) but low CTR ({avg_ctr:.1%})",
                    }
                )

            # Foxes = high bounce rate (from GA4)
            avg_bounce = await db.fetchval(
                """
                SELECT AVG(gm.bounce_rate) FROM ga4_metrics gm
                JOIN post_clusters pc ON pc.post_id = gm.post_id
                WHERE pc.cluster_id = $1
                """,
                cid,
            )

            if avg_bounce is not None and avg_bounce > 0.7:
                fox_count = min(int((avg_bounce - 0.7) * 10), 3)
                cluster_animals.append(
                    {
                        "type": "foxes",
                        "count": max(fox_count, 1),
                        "meaning": f"High bounce rate ({avg_bounce:.0%})",
                    }
                )

            # Deer = high engagement (avg_session_duration > 180s)
            avg_engagement = await db.fetchval(
                """
                SELECT AVG(gm.avg_session_duration) FROM ga4_metrics gm
                JOIN post_clusters pc ON pc.post_id = gm.post_id
                WHERE pc.cluster_id = $1
                """,
                cid,
            )

            if avg_engagement is not None and avg_engagement > 180:
                deer_count = min(int(avg_engagement / 120), 3)
                cluster_animals.append(
                    {
                        "type": "deer",
                        "count": max(deer_count, 1),
                        "meaning": f"High engagement ({avg_engagement:.0f}s avg)",
                    }
                )

            # Bees = high CTR + high impressions = popular content
            if (
                avg_ctr is not None
                and avg_ctr > 0.05
                and avg_impressions is not None
                and avg_impressions > 1000
            ):
                cluster_animals.append(
                    {
                        "type": "bees",
                        "count": 2,
                        "meaning": "High visibility and engagement — attracting external attention",
                    }
                )

            # Vultures = declining posts
            declining_posts = await db.fetchval(
                """
                SELECT COUNT(*) FROM post_health_scores phs
                JOIN post_clusters pc ON pc.post_id = phs.post_id
                WHERE pc.cluster_id = $1 AND phs.trend = 'declining'
                """,
                cid,
            )

            if declining_posts is not None and declining_posts >= 2:
                cluster_animals.append(
                    {
                        "type": "vultures",
                        "count": min(declining_posts, 3),
                        "meaning": f"{declining_posts} posts losing rankings",
                    }
                )

            animals[str(cid)] = cluster_animals

        return animals

    async def _compute_terrain_features(
        self, db: asyncpg.Connection, clusters: list[dict]
    ) -> dict[str, list[dict]]:
        """Detect structural issues and map to terrain features."""
        features: dict[str, list[dict]] = {}

        for cluster in clusters:
            cid = cluster["id"]
            cluster_features: list[dict] = []

            # Boulders = broken internal links (404s)
            broken_links = await db.fetchval(
                """
                SELECT COUNT(*) FROM internal_links il
                JOIN post_clusters pc ON pc.post_id = il.source_post_id
                WHERE pc.cluster_id = $1 AND il.status_code = 404
                """,
                cid,
            )

            if broken_links and broken_links > 0:
                cluster_features.append(
                    {
                        "type": "boulders",
                        "count": min(broken_links, 5),
                        "meaning": f"{broken_links} broken internal links",
                    }
                )

            # Erosion = thin content (< 500 words)
            thin_posts = await db.fetchval(
                """
                SELECT COUNT(*) FROM posts p
                JOIN post_clusters pc ON pc.post_id = p.id
                WHERE pc.cluster_id = $1 AND p.word_count < 500
                """,
                cid,
            )

            if thin_posts and thin_posts > 0:
                cluster_features.append(
                    {
                        "type": "erosion",
                        "count": thin_posts,
                        "meaning": f"{thin_posts} thin posts (< 500 words)",
                    }
                )

            # Mushrooms = near-duplicate content (overlap > 0.8)
            duplicates = await db.fetchval(
                """
                SELECT COUNT(*) FROM cannibalization_pairs cp
                WHERE cp.cluster_id = $1 AND cp.overlap_score > 0.8
                """,
                cid,
            )

            if duplicates and duplicates > 0:
                cluster_features.append(
                    {
                        "type": "mushrooms",
                        "count": min(duplicates * 2, 6),
                        "meaning": f"{duplicates} near-duplicate post pairs",
                    }
                )

            features[str(cid)] = cluster_features

        return features

    async def _compute_water_quality(
        self, db: asyncpg.Connection, rivers: list[dict]
    ) -> list[dict]:
        """Enhance river data with engagement-based water quality."""
        for river in rivers:
            from_engagement = await self._get_cluster_engagement(
                db, river["from_cluster_id"]
            )
            to_engagement = await self._get_cluster_engagement(
                db, river["to_cluster_id"]
            )

            avg_engagement = (from_engagement + to_engagement) / 2

            if avg_engagement > 0.7:
                river["quality"] = "sparkling"
            elif avg_engagement > 0.4:
                river["quality"] = "clear"
            elif avg_engagement > 0.2:
                river["quality"] = "murky"
            else:
                river["quality"] = "toxic"

        return rivers

    async def _get_cluster_engagement(
        self, db: asyncpg.Connection, cluster_id: str
    ) -> float:
        """Get average engagement score for a cluster (0-1 scale)."""
        avg_health = await db.fetchval(
            """
            SELECT AVG(phs.composite_score) FROM post_health_scores phs
            JOIN post_clusters pc ON pc.post_id = phs.post_id
            WHERE pc.cluster_id = $1::uuid
            """,
            cluster_id,
        )
        if avg_health is None:
            return 0.0
        # Normalize health_score (assumed 0-100) to 0-1
        return min(max(float(avg_health) / 100.0, 0.0), 1.0)
