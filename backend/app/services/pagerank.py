"""Internal PageRank — link authority flow analysis.

Runs Google's PageRank algorithm on the site's internal link graph
using networkx. Every post gets an Internal Authority Score showing
how much link juice flows to it from the rest of the site.

This goes beyond binary "has links / doesn't have links" to show
WHICH posts are distributing authority and which are hoarding it.

A pillar post with 50 inbound links from dead-weight pages is
different from one with 5 inbound links from other pillars.
"""

import asyncio
import logging
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class InternalPageRank:
    """Compute PageRank on internal link graph."""

    async def compute_for_site(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Compute internal PageRank for all posts in a site.

        Uses networkx.pagerank() on the directed graph of internal links.
        Stores normalized scores (0-1) on post_health_scores.

        Returns the number of posts scored.
        """
        logger.info("Computing internal PageRank for site %s", site_id)

        # Get all internal links for this site
        links = await db.fetch(
            """
            SELECT il.source_post_id, il.target_post_id
            FROM internal_links il
            JOIN posts ps ON ps.id = il.source_post_id
            JOIN posts pt ON pt.id = il.target_post_id
            WHERE ps.site_id = $1 AND pt.site_id = $1
            """,
            site_id,
        )

        # Get all post IDs (including those with no links)
        all_posts = await db.fetch(
            "SELECT id FROM posts WHERE site_id = $1", site_id,
        )
        all_post_ids = {r["id"] for r in all_posts}

        if not all_post_ids:
            return 0

        if not links:
            # No internal links — give everyone equal PageRank
            equal_rank = 1.0 / len(all_post_ids)
            await self._store_pageranks(db, {pid: equal_rank for pid in all_post_ids})
            logger.info("No internal links for site %s — equal PageRank assigned", site_id)
            return len(all_post_ids)

        # Quality gate: check link resolution rate.
        # If only a small fraction of internal links resolved to known posts
        # (e.g., capped crawl at 150 of 3000 URLs → 4% resolution), the link
        # graph is too sparse for meaningful PageRank. Most nodes would be
        # disconnected and get near-equal scores, making the metric useless.
        # In this case, assign equal PageRank and log a warning.
        MIN_RESOLUTION_RATE = 0.20  # 20% of links must resolve
        total_links = await db.fetchval(
            """SELECT COUNT(*) FROM internal_links il
               JOIN posts p ON p.id = il.source_post_id
               WHERE p.site_id = $1""",
            site_id,
        )
        resolution_rate = len(links) / max(total_links, 1)
        if resolution_rate < MIN_RESOLUTION_RATE:
            equal_rank = 1.0 / len(all_post_ids)
            await self._store_pageranks(db, {pid: equal_rank for pid in all_post_ids})
            logger.warning(
                "PageRank skipped for site %s: link resolution %.1f%% < %.0f%% threshold "
                "(only %d of %d links resolved — likely a capped crawl). "
                "Equal PageRank assigned.",
                site_id, resolution_rate * 100, MIN_RESOLUTION_RATE * 100,
                len(links), total_links,
            )
            return len(all_post_ids)

        # Build graph and compute PageRank in thread (CPU-bound)
        edges = [(r["source_post_id"], r["target_post_id"]) for r in links]
        pageranks = await asyncio.to_thread(
            self._compute_pagerank, edges, all_post_ids,
        )

        # Store results
        await self._store_pageranks(db, pageranks)

        logger.info(
            "Internal PageRank computed for %d posts (%.0f%% link resolution) in site %s",
            len(pageranks), resolution_rate * 100, site_id,
        )
        return len(pageranks)

    @staticmethod
    def _compute_pagerank(
        edges: list[tuple], all_nodes: set,
    ) -> dict:
        """Build directed graph and compute PageRank.

        Uses networkx — offloaded to thread.
        """
        import networkx as nx

        G = nx.DiGraph()
        G.add_nodes_from(all_nodes)
        G.add_edges_from(edges)

        # Compute PageRank (alpha=0.85 is the standard damping factor)
        try:
            pr = nx.pagerank(G, alpha=0.85, max_iter=100, tol=1e-6)
        except nx.PowerIterationFailedConvergence:
            # Fallback: use simpler computation
            pr = nx.pagerank(G, alpha=0.85, max_iter=200, tol=1e-4)

        return pr

    @staticmethod
    async def _store_pageranks(
        db: asyncpg.Connection, pageranks: dict,
    ) -> None:
        """Store PageRank scores on post_health_scores (batch update)."""
        batch_data = [(float(rank), post_id) for post_id, rank in pageranks.items()]
        await db.executemany(
            """
            UPDATE post_health_scores
            SET internal_pagerank = $1
            WHERE post_id = $2
            """,
            batch_data,
        )

    @staticmethod
    async def detect_broken_links(
        db: asyncpg.Connection, site_id: UUID,
    ) -> int:
        """Detect internal links pointing to non-existent or error pages.

        Returns the count of broken links found.
        """
        broken = await db.fetch("""
            SELECT il.source_post_id, il.target_url,
                   ps.title as source_title
            FROM internal_links il
            JOIN posts ps ON ps.id = il.source_post_id
            LEFT JOIN posts pt ON pt.url = il.target_url AND pt.site_id = $1
            WHERE ps.site_id = $1
              AND pt.id IS NULL
              AND il.target_url LIKE '%' || (
                  SELECT domain FROM sites WHERE id = $1
              ) || '%'
        """, site_id)

        logger.info("Found %d broken internal links for site %s", len(broken), site_id)
        return len(broken)

    @staticmethod
    async def count_outbound_links(
        db: asyncpg.Connection, site_id: UUID,
    ) -> dict[UUID, int]:
        """Count external (outbound) links per post.

        Posts with 0 outbound links lack citations — a content quality signal.
        """
        rows = await db.fetch("""
            SELECT il.source_post_id, count(*) as cnt
            FROM internal_links il
            JOIN posts p ON p.id = il.source_post_id
            WHERE p.site_id = $1
              AND il.target_url NOT LIKE '%' || (
                  SELECT domain FROM sites WHERE id = $1
              ) || '%'
            GROUP BY il.source_post_id
        """, site_id)
        return {r["source_post_id"]: r["cnt"] for r in rows}
