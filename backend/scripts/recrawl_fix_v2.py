"""Re-crawl v2 — batch approach: fetch 1 at a time, write immediately.
Sequential to avoid asyncpg concurrency issues.
"""

import asyncio
import logging
import os
import sys
import time
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/recrawl_v2.log", mode="w"),
    ],
)
logger = logging.getLogger(__name__)

DEFAULT_SITE_ID = "32296e5d-7924-4d9f-92b8-7f774c634fad"
DOMAIN = "close.com"


async def main():
    from dotenv import load_dotenv
    load_dotenv()

    import asyncpg
    import httpx
    import trafilatura
    from bs4 import BeautifulSoup
    from app.services.normalizer import compute_content_hash
    from app.utils.url_normalize import normalize_url

    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    site_id = UUID(sys.argv[1]) if len(sys.argv) > 1 else UUID(DEFAULT_SITE_ID)

    try:
        posts = await conn.fetch(
            "SELECT id, url, title, body_html FROM posts WHERE site_id = $1 ORDER BY publish_date ASC",
            site_id,
        )
        total = len(posts)
        logger.info("Re-crawling %d posts sequentially...", total)

        stats = {"updated": 0, "images": 0, "errors": 0, "skipped": 0}
        t_start = time.time()

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Enough/0.1 (Content Intelligence Bot)"},
            follow_redirects=True,
        ) as client:
            for i, post in enumerate(posts):
                url = post["url"]
                post_id = post["id"]

                try:
                    await asyncio.sleep(0.3)  # Rate limit
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning("[%d/%d] HTTP %d: %s", i+1, total, resp.status_code, url[-40:])
                        stats["errors"] += 1
                        continue

                    html = resp.text
                    soup = BeautifulSoup(html, "lxml")

                    # body_html — real HTML with images
                    main = (
                        soup.find("main") or soup.find("article")
                        or soup.find("div", class_=lambda c: c and ("content" in c.lower() or "post" in c.lower()))
                        or soup.find("body")
                    )
                    body_html = str(main) if main else ""
                    has_img = "<img" in body_html
                    if has_img:
                        stats["images"] += 1

                    # body_text
                    body_text = trafilatura.extract(html) or ""
                    if len(body_text.strip()) < 50:
                        stats["skipped"] += 1
                        continue

                    word_count = len(body_text.split())
                    content_hash = compute_content_hash(body_text)

                    # meta_description
                    meta_tag = soup.find("meta", attrs={"name": "description"})
                    meta_desc = meta_tag.get("content", "").strip() if meta_tag else None

                    # headings
                    headings = []
                    for tag in soup.find_all(re.compile(r"^h[1-6]$")):
                        text = tag.get_text(strip=True)
                        if text:
                            headings.append({"level": tag.name, "text": text})
                    headings_json = json.dumps(headings) if headings else None

                    # internal links — no self-links, no dupes
                    links = []
                    seen = set()
                    current_norm = normalize_url(url)
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        p = urlparse(href)
                        if not p.netloc:
                            href = urljoin(url, href)
                            p = urlparse(href)
                        if p.netloc.lower().replace("www.", "") == DOMAIN:
                            nh = normalize_url(href)
                            if nh != current_norm and nh not in seen:
                                seen.add(nh)
                                links.append((nh, a.get_text(strip=True) or None))

                    # Write to DB
                    await conn.execute("""
                        UPDATE posts SET
                            body_html=$1, body_text=$2, word_count=$3, content_hash=$4,
                            meta_description=COALESCE($5, meta_description),
                            headings=COALESCE($6, headings),
                            http_status=$7, updated_at=NOW()
                        WHERE id=$8
                    """, body_html, body_text, word_count, content_hash,
                        meta_desc, headings_json, resp.status_code, post_id)

                    await conn.execute("DELETE FROM internal_links WHERE source_post_id = $1", post_id)
                    if links:
                        await conn.executemany("""
                            INSERT INTO internal_links (site_id, source_post_id, target_url, anchor_text)
                            VALUES ($1, $2, $3, $4)
                        """, [(site_id, post_id, h, a) for h, a in links])

                    stats["updated"] += 1

                    if (i+1) % 50 == 0:
                        elapsed = time.time() - t_start
                        rate = (i+1) / elapsed
                        eta = (total - i - 1) / rate
                        logger.info("[%d/%d] %.1f/s, ETA %.0fs | updated=%d img=%d err=%d",
                                    i+1, total, rate, eta, stats["updated"], stats["images"], stats["errors"])

                except Exception as e:
                    logger.error("[%d/%d] %s: %s", i+1, total, url[-40:], str(e)[:80])
                    stats["errors"] += 1

        # Resolve link targets
        logger.info("Resolving link targets...")
        await conn.execute("""
            UPDATE internal_links il SET target_post_id = p.id
            FROM posts p
            WHERE il.site_id = $1 AND p.site_id = $1
              AND il.target_url = p.url AND il.target_post_id IS NULL
        """, site_id)
        # Try with/without trailing slash
        await conn.execute("""
            UPDATE internal_links il SET target_post_id = p.id
            FROM posts p
            WHERE il.site_id = $1 AND p.site_id = $1
              AND (il.target_url || '/' = p.url OR il.target_url = p.url || '/')
              AND il.target_post_id IS NULL
        """, site_id)

        elapsed = time.time() - t_start
        logger.info("=" * 60)
        logger.info("COMPLETE in %.1fs (%.1f min)", elapsed, elapsed / 60)
        for k, v in stats.items():
            logger.info("  %s: %s", k, v)

        # Verification
        traf = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id=$1 AND body_html LIKE '<doc%'", site_id)
        imgs = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id=$1 AND body_html LIKE '%<img%'", site_id)
        links_total = await conn.fetchval("SELECT count(*) FROM internal_links WHERE source_post_id IN (SELECT id FROM posts WHERE site_id=$1)", site_id)
        resolved = await conn.fetchval("SELECT count(*) FROM internal_links WHERE source_post_id IN (SELECT id FROM posts WHERE site_id=$1) AND target_post_id IS NOT NULL", site_id)
        self_links = await conn.fetchval("SELECT count(*) FROM internal_links WHERE source_post_id IN (SELECT id FROM posts WHERE site_id=$1) AND source_post_id=target_post_id", site_id)
        orphans = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id=$1 AND id NOT IN (SELECT DISTINCT target_post_id FROM internal_links WHERE target_post_id IS NOT NULL)", site_id)

        logger.info("\nVERIFICATION:")
        logger.info("  Trafilatura XML remaining: %d", traf)
        logger.info("  Posts with <img>: %d", imgs)
        logger.info("  Total links: %d", links_total)
        logger.info("  Resolved: %d (%.1f%%)", resolved, resolved*100/links_total if links_total else 0)
        logger.info("  Self-links: %d", self_links)
        logger.info("  Orphan posts: %d", orphans)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
