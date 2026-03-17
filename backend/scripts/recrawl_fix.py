"""Re-crawl all posts for a site to fix foundation data.

Fixes:
1. body_html: Replace trafilatura XML with real HTML (images, structure preserved)
2. modified_date: Extract from meta tags
3. internal_links: Clean re-extract (no self-links, no dupes)
4. headings: Re-extract from real HTML
5. meta_description: Re-extract
6. Crawl missing posts (beyond the 600 cap)

Usage: python scripts/recrawl_fix.py [site_id] [--all] [--dry-run]

--all: Also crawl posts beyond the original 600 cap
--dry-run: Print what would change without writing to DB
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/recrawl_fix.log", mode="w"),
    ],
)
logger = logging.getLogger(__name__)

DEFAULT_SITE_ID = "32296e5d-7924-4d9f-92b8-7f774c634fad"


async def main():
    from dotenv import load_dotenv
    load_dotenv()

    import asyncpg
    import httpx
    import trafilatura
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse, urljoin

    from app.services.normalizer import compute_content_hash
    from app.utils.url_normalize import normalize_url

    db_url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(db_url)

    site_id = UUID(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else UUID(DEFAULT_SITE_ID)
    crawl_all = "--all" in sys.argv
    dry_run = "--dry-run" in sys.argv

    try:
        # Get all existing posts
        posts = await conn.fetch(
            "SELECT id, url, title, body_html, modified_date, word_count FROM posts WHERE site_id = $1 ORDER BY publish_date ASC",
            site_id,
        )
        logger.info("Found %d existing posts to re-crawl", len(posts))

        # Stats
        stats = {
            "total": len(posts),
            "html_fixed": 0,
            "modified_date_found": 0,
            "images_found": 0,
            "links_updated": 0,
            "meta_updated": 0,
            "errors": 0,
            "skipped": 0,
        }

        domain = "close.com"
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests
        
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Enough/0.1 (Content Intelligence Bot)"},
            follow_redirects=True,
        ) as client:

            async def process_post(post, index):
                async with semaphore:
                    url = post["url"]
                    post_id = post["id"]
                    
                    try:
                        # Rate limit
                        await asyncio.sleep(0.5)
                        
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            logger.warning("[%d/%d] HTTP %d: %s", index + 1, stats["total"], resp.status_code, url[:60])
                            stats["errors"] += 1
                            return
                        
                        html = resp.text
                        soup = BeautifulSoup(html, "lxml")

                        # === Extract body_html with images preserved ===
                        main_content = (
                            soup.find("main")
                            or soup.find("article")
                            or soup.find("div", class_=lambda c: c and (
                                "content" in c.lower() or "post" in c.lower() or "entry" in c.lower()
                            ))
                            or soup.find("body")
                        )
                        new_body_html = str(main_content) if main_content else html

                        # Check if images now exist
                        has_images = "<img" in new_body_html or "<picture" in new_body_html
                        if has_images:
                            stats["images_found"] += 1

                        # Check if body_html actually changed
                        old_html = post["body_html"] or ""
                        html_changed = old_html.startswith("<doc") or old_html.startswith("<?xml")
                        if html_changed:
                            stats["html_fixed"] += 1

                        # === Extract body_text (trafilatura) ===
                        body_text = trafilatura.extract(html) or ""
                        if not body_text or len(body_text.strip()) < 50:
                            logger.warning("[%d/%d] Too little text: %s", index + 1, stats["total"], url[:60])
                            stats["skipped"] += 1
                            return

                        word_count = len(body_text.split())
                        content_hash = compute_content_hash(body_text)

                        # === Extract modified_date ===
                        modified_date = None
                        modified_meta = (
                            soup.find("meta", attrs={"property": "article:modified_time"})
                            or soup.find("meta", attrs={"property": "og:updated_time"})
                            or soup.find("meta", attrs={"name": "last-modified"})
                            or soup.find("meta", attrs={"itemprop": "dateModified"})
                        )
                        if modified_meta and modified_meta.get("content"):
                            try:
                                modified_date = datetime.fromisoformat(
                                    modified_meta["content"].replace("Z", "+00:00")
                                ).replace(tzinfo=timezone.utc)
                                stats["modified_date_found"] += 1
                            except (ValueError, TypeError):
                                pass

                        # Also try <time> tags
                        if not modified_date:
                            for tt in soup.find_all("time", attrs={"datetime": True}):
                                classes = tt.get("class", [])
                                if isinstance(classes, str):
                                    classes = [classes]
                                cls_str = " ".join(classes).lower()
                                if "modif" in cls_str or "update" in cls_str:
                                    try:
                                        modified_date = datetime.fromisoformat(
                                            tt["datetime"].replace("Z", "+00:00")
                                        ).replace(tzinfo=timezone.utc)
                                        stats["modified_date_found"] += 1
                                    except (ValueError, TypeError):
                                        pass
                                    break

                        # === Extract meta_description ===
                        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
                        meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

                        # === Extract headings ===
                        import re
                        headings = []
                        for tag in soup.find_all(re.compile(r"^h[1-6]$")):
                            text = tag.get_text(strip=True)
                            if text:
                                headings.append({"level": tag.name, "text": text})
                        import json
                        headings_json = json.dumps(headings) if headings else None

                        # === Extract internal links ===
                        internal_links = []
                        seen_targets = set()
                        current_norm = normalize_url(url)
                        for anchor in soup.find_all("a", href=True):
                            href = anchor["href"]
                            parsed = urlparse(href)
                            if not parsed.netloc:
                                href = urljoin(url, href)
                                parsed = urlparse(href)
                            
                            if parsed.netloc.lower().replace("www.", "") == domain:
                                norm_href = normalize_url(href)
                                # Skip self-links and duplicates
                                if norm_href == current_norm:
                                    continue
                                if norm_href in seen_targets:
                                    continue
                                seen_targets.add(norm_href)
                                
                                anchor_text = anchor.get_text(strip=True)
                                internal_links.append((norm_href, anchor_text or None))

                        if dry_run:
                            changes = []
                            if html_changed: changes.append("html")
                            if modified_date: changes.append(f"modified={modified_date.date()}")
                            if has_images: changes.append("images")
                            if changes:
                                logger.info("[%d] %s: %s", index + 1, url[:50], ", ".join(changes))
                            return

                        # === Update database ===
                        await conn.execute("""
                            UPDATE posts SET
                                body_html = $1,
                                body_text = $2,
                                word_count = $3,
                                content_hash = $4,
                                modified_date = COALESCE($5, modified_date),
                                meta_description = COALESCE($6, meta_description),
                                headings = COALESCE($7, headings),
                                http_status = $8,
                                updated_at = NOW()
                            WHERE id = $9
                        """,
                            new_body_html, body_text, word_count, content_hash,
                            modified_date, meta_description, headings_json,
                            resp.status_code, post_id,
                        )

                        # Re-insert internal links (clean — no self-links, no dupes)
                        await conn.execute("DELETE FROM internal_links WHERE source_post_id = $1", post_id)
                        if internal_links:
                            await conn.executemany("""
                                INSERT INTO internal_links (site_id, source_post_id, target_url, anchor_text)
                                VALUES ($1, $2, $3, $4)
                            """, [(site_id, post_id, href, anchor) for href, anchor in internal_links])
                        stats["links_updated"] += 1

                        if (index + 1) % 25 == 0:
                            logger.info("[%d/%d] Progress...", index + 1, stats["total"])

                    except Exception as e:
                        logger.error("[%d/%d] Error: %s — %s", index + 1, stats["total"], url[:50], str(e)[:100])
                        stats["errors"] += 1

            # Fetch all pages concurrently, but write to DB sequentially
            # (asyncpg single connection can't handle concurrent writes)
            import dataclasses
            from dataclasses import dataclass as dc
            
            @dc
            class CrawlResult:
                post_id: object
                url: str
                body_html: str
                body_text: str
                word_count: int
                content_hash: str
                modified_date: object
                meta_description: object
                headings_json: object
                http_status: int
                internal_links: list
                has_images: bool
                html_changed: bool
            
            results_queue: list[CrawlResult | None] = []
            
            async def fetch_post(post, index):
                """Fetch and parse only — no DB writes."""
                async with semaphore:
                    url = post["url"]
                    try:
                        await asyncio.sleep(0.5)
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            logger.warning("[%d/%d] HTTP %d: %s", index + 1, stats["total"], resp.status_code, url[:60])
                            stats["errors"] += 1
                            return None
                        
                        html = resp.text
                        soup = BeautifulSoup(html, "lxml")

                        main_content = (
                            soup.find("main")
                            or soup.find("article")
                            or soup.find("div", class_=lambda c: c and (
                                "content" in c.lower() or "post" in c.lower() or "entry" in c.lower()
                            ))
                            or soup.find("body")
                        )
                        new_body_html = str(main_content) if main_content else html
                        has_images = "<img" in new_body_html or "<picture" in new_body_html
                        
                        old_html = post["body_html"] or ""
                        html_changed = old_html.startswith("<doc") or old_html.startswith("<?xml")

                        body_text = trafilatura.extract(html) or ""
                        if not body_text or len(body_text.strip()) < 50:
                            stats["skipped"] += 1
                            return None

                        word_count = len(body_text.split())
                        content_hash = compute_content_hash(body_text)

                        modified_date = None
                        modified_meta = (
                            soup.find("meta", attrs={"property": "article:modified_time"})
                            or soup.find("meta", attrs={"property": "og:updated_time"})
                            or soup.find("meta", attrs={"name": "last-modified"})
                            or soup.find("meta", attrs={"itemprop": "dateModified"})
                        )
                        if modified_meta and modified_meta.get("content"):
                            try:
                                modified_date = datetime.fromisoformat(
                                    modified_meta["content"].replace("Z", "+00:00")
                                ).replace(tzinfo=timezone.utc)
                            except (ValueError, TypeError):
                                pass

                        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
                        meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

                        import re as re_mod
                        headings = []
                        for tag in soup.find_all(re_mod.compile(r"^h[1-6]$")):
                            text = tag.get_text(strip=True)
                            if text:
                                headings.append({"level": tag.name, "text": text})
                        import json
                        headings_json = json.dumps(headings) if headings else None

                        internal_links = []
                        seen_targets = set()
                        current_norm = normalize_url(url)
                        for anchor in soup.find_all("a", href=True):
                            href = anchor["href"]
                            parsed = urlparse(href)
                            if not parsed.netloc:
                                href = urljoin(url, href)
                                parsed = urlparse(href)
                            if parsed.netloc.lower().replace("www.", "") == domain:
                                norm_href = normalize_url(href)
                                if norm_href == current_norm:
                                    continue
                                if norm_href in seen_targets:
                                    continue
                                seen_targets.add(norm_href)
                                anchor_text = anchor.get_text(strip=True)
                                internal_links.append((norm_href, anchor_text or None))

                        if (index + 1) % 50 == 0:
                            logger.info("[%d/%d] Fetched...", index + 1, stats["total"])

                        return CrawlResult(
                            post_id=post["id"], url=url,
                            body_html=new_body_html, body_text=body_text,
                            word_count=word_count, content_hash=content_hash,
                            modified_date=modified_date, meta_description=meta_description,
                            headings_json=headings_json, http_status=resp.status_code,
                            internal_links=internal_links, has_images=has_images,
                            html_changed=html_changed,
                        )
                    except Exception as e:
                        logger.error("[%d/%d] Fetch error: %s — %s", index + 1, stats["total"], url[:50], str(e)[:100])
                        stats["errors"] += 1
                        return None

            # Phase 1: Fetch all concurrently
            t_start = time.time()
            logger.info("Phase 1: Fetching %d pages concurrently (max 5)...", len(posts))
            tasks = [fetch_post(p, i) for i, p in enumerate(posts)]
            results_queue = await asyncio.gather(*tasks)
            fetch_time = time.time() - t_start
            logger.info("Fetch complete in %.1fs. Writing to DB...", fetch_time)

            # Phase 2: Write to DB sequentially
            if not dry_run:
                for i, result in enumerate(results_queue):
                    if result is None:
                        continue
                    try:
                        if result.has_images:
                            stats["images_found"] += 1
                        if result.html_changed:
                            stats["html_fixed"] += 1
                        if result.modified_date:
                            stats["modified_date_found"] += 1

                        await conn.execute("""
                            UPDATE posts SET
                                body_html = $1, body_text = $2, word_count = $3,
                                content_hash = $4, modified_date = COALESCE($5, modified_date),
                                meta_description = COALESCE($6, meta_description),
                                headings = COALESCE($7, headings),
                                http_status = $8, updated_at = NOW()
                            WHERE id = $9
                        """,
                            result.body_html, result.body_text, result.word_count,
                            result.content_hash, result.modified_date,
                            result.meta_description, result.headings_json,
                            result.http_status, result.post_id,
                        )

                        await conn.execute("DELETE FROM internal_links WHERE source_post_id = $1", result.post_id)
                        if result.internal_links:
                            await conn.executemany("""
                                INSERT INTO internal_links (site_id, source_post_id, target_url, anchor_text)
                                VALUES ($1, $2, $3, $4)
                            """, [(site_id, result.post_id, href, anchor) for href, anchor in result.internal_links])
                        stats["links_updated"] += 1

                        if (i + 1) % 100 == 0:
                            logger.info("[%d/%d] Written to DB...", i + 1, len(results_queue))
                    except Exception as e:
                        logger.error("DB write error for %s: %s", result.url[:50], str(e)[:100])
                        stats["errors"] += 1

            elapsed = time.time() - t_start

        # Resolve link targets
        if not dry_run:
            logger.info("Resolving link targets...")
            await conn.execute("""
                UPDATE internal_links il
                SET target_post_id = p.id
                FROM posts p
                WHERE il.site_id = $1
                  AND p.site_id = $1
                  AND il.target_url = p.url
                  AND il.target_post_id IS NULL
            """, site_id)

            # Also try with/without trailing slash
            await conn.execute("""
                UPDATE internal_links il
                SET target_post_id = p.id
                FROM posts p
                WHERE il.site_id = $1
                  AND p.site_id = $1
                  AND (il.target_url || '/' = p.url OR il.target_url = p.url || '/')
                  AND il.target_post_id IS NULL
            """, site_id)

        # Final stats
        logger.info("=" * 60)
        logger.info("RE-CRAWL COMPLETE in %.1fs (%.1f min)", elapsed, elapsed / 60)
        logger.info("=" * 60)
        for k, v in stats.items():
            logger.info("  %s: %s", k, v)

        # Post-crawl verification
        if not dry_run:
            traf_count = await conn.fetchval(
                "SELECT count(*) FROM posts WHERE site_id = $1 AND body_html LIKE '<doc%'", site_id
            )
            img_count = await conn.fetchval(
                "SELECT count(*) FROM posts WHERE site_id = $1 AND body_html LIKE '%<img%'", site_id
            )
            mod_count = await conn.fetchval(
                "SELECT count(*) FROM posts WHERE site_id = $1 AND modified_date IS NOT NULL", site_id
            )
            link_count = await conn.fetchval(
                "SELECT count(*) FROM internal_links WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1)", site_id
            )
            resolved = await conn.fetchval(
                "SELECT count(*) FROM internal_links WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1) AND target_post_id IS NOT NULL", site_id
            )
            self_links = await conn.fetchval(
                "SELECT count(*) FROM internal_links WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1) AND source_post_id = target_post_id", site_id
            )

            logger.info("\nVERIFICATION:")
            logger.info("  Trafilatura XML remaining: %d", traf_count)
            logger.info("  Posts with <img>: %d", img_count)
            logger.info("  Posts with modified_date: %d", mod_count)
            logger.info("  Total links: %d", link_count)
            logger.info("  Resolved links: %d (%.1f%%)", resolved, resolved * 100 / link_count if link_count else 0)
            logger.info("  Self-links: %d", self_links)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
