"""Re-resolve internal_links.target_post_id using improved URL normalization.

Builds a normalized URL → post_id lookup for all posts, then batch-updates
target_post_id for all unresolved links whose target_url matches a known post.
"""
import asyncio
import logging
import os
import sys
import time
from uuid import UUID

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.utils.url_normalize import normalize_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

SITE_ID = UUID("32296e5d-7924-4d9f-92b8-7f774c634fad")


async def main():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    t0 = time.time()

    # Build normalized URL → post_id map
    posts = await conn.fetch(
        "SELECT id, url FROM posts WHERE site_id = $1", SITE_ID
    )
    url_map: dict[str, UUID] = {}
    for p in posts:
        norm = normalize_url(p["url"])
        url_map[norm] = p["id"]
        # Also store without www and with www variants
        if "www." not in norm:
            url_map[norm.replace("://", "://www.")] = p["id"]
    log.info("Built URL map: %d normalized URLs for %d posts", len(url_map), len(posts))

    # Count current resolution state
    total = await conn.fetchval("SELECT COUNT(*) FROM internal_links WHERE site_id = $1", SITE_ID)
    already_resolved = await conn.fetchval(
        "SELECT COUNT(*) FROM internal_links WHERE site_id = $1 AND target_post_id IS NOT NULL", SITE_ID
    )
    log.info("Current: %d/%d resolved (%.1f%%)", already_resolved, total, 100 * already_resolved / total if total else 0)

    # Fetch all unresolved links
    unresolved = await conn.fetch(
        "SELECT id, target_url FROM internal_links WHERE site_id = $1 AND target_post_id IS NULL",
        SITE_ID,
    )
    log.info("Unresolved links to process: %d", len(unresolved))

    resolved = 0
    batch = []
    for link in unresolved:
        target_url = link["target_url"]
        if not target_url:
            continue
        norm = normalize_url(target_url)
        post_id = url_map.get(norm)
        if post_id:
            batch.append((post_id, link["id"]))
            resolved += 1

        if len(batch) >= 500:
            await conn.executemany(
                "UPDATE internal_links SET target_post_id = $1 WHERE id = $2",
                batch,
            )
            batch = []

    if batch:
        await conn.executemany(
            "UPDATE internal_links SET target_post_id = $1 WHERE id = $2",
            batch,
        )

    # Final stats
    new_resolved = await conn.fetchval(
        "SELECT COUNT(*) FROM internal_links WHERE site_id = $1 AND target_post_id IS NOT NULL", SITE_ID
    )
    log.info(
        "Done in %.1fs. Resolved: %d → %d (+%d) = %.1f%% of %d",
        time.time() - t0,
        already_resolved, new_resolved, new_resolved - already_resolved,
        100 * new_resolved / total if total else 0,
        total,
    )
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
