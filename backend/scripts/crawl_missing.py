"""Crawl the 359 missing blog posts to complete the graph."""
import asyncio, asyncpg, gc, httpx, json, logging, os, re, sys, time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

from app.services.normalizer import compute_content_hash
from app.utils.url_normalize import normalize_url

SITE_ID = UUID("32296e5d-7924-4d9f-92b8-7f774c634fad")
DOMAIN = "close.com"

async def main():
    from dotenv import load_dotenv
    load_dotenv()
    import trafilatura
    from bs4 import BeautifulSoup
    
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    
    # Read missing URLs
    with open("/tmp/missing_urls.txt") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    total = len(urls)
    log.info("Crawling %d missing posts", total)
    
    stats = {"ok": 0, "img": 0, "err": 0, "skip": 0}
    t0 = time.time()
    
    client = httpx.Client(timeout=30, headers={"User-Agent": "Tended/0.1"}, follow_redirects=True)
    
    for i, url in enumerate(urls):
        try:
            time.sleep(0.2)
            resp = client.get(url)
            if resp.status_code != 200:
                log.warning("[%d/%d] HTTP %d: %s", i+1, total, resp.status_code, url[-40:])
                stats["err"] += 1
                continue
            
            html = resp.text
            body_text = trafilatura.extract(html) or ""
            if len(body_text.strip()) < 50:
                stats["skip"] += 1
                del html, body_text; gc.collect()
                continue
            
            soup = BeautifulSoup(html, "lxml")
            del html; gc.collect()
            
            # title
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""
            # Strip site name
            for sep in [" | ", " – ", " — ", " - "]:
                if sep in title:
                    parts = title.split(sep)
                    if len(parts[-1].split()) <= 4:
                        title = sep.join(parts[:-1])
                    break
            
            # body_html
            main = soup.find("main") or soup.find("article") or soup.find("body")
            body_html = str(main) if main else ""
            has_img = "<img" in body_html
            if has_img: stats["img"] += 1
            
            # meta
            mt = soup.find("meta", attrs={"name": "description"})
            meta = mt.get("content", "").strip() if mt else None
            
            # publish date
            metadata = trafilatura.extract_metadata(resp.text if hasattr(resp, '_content') else str(soup))
            publish_date = None
            if metadata and metadata.date:
                try:
                    publish_date = datetime.fromisoformat(str(metadata.date)).replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass
            if not publish_date:
                pub_meta = soup.find("meta", attrs={"property": "article:published_time"})
                if pub_meta and pub_meta.get("content"):
                    try:
                        publish_date = datetime.fromisoformat(pub_meta["content"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                    except: pass
            # time tag fallback
            if not publish_date:
                for tt in soup.find_all("time", attrs={"datetime": True}):
                    try:
                        publish_date = datetime.fromisoformat(tt["datetime"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                        break
                    except: pass
            
            # headings
            hds = [{"level": t.name, "text": t.get_text(strip=True)} for t in soup.find_all(re.compile(r"^h[1-6]$")) if t.get_text(strip=True)]
            hj = json.dumps(hds) if hds else None
            
            # slug
            parsed = urlparse(url)
            slug = parsed.path.strip("/").split("/")[-1] if parsed.path.strip("/") else None
            
            # links
            links = []
            seen = set()
            cn = normalize_url(url)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                p = urlparse(href)
                if not p.netloc: href = urljoin(url, href); p = urlparse(href)
                if p.netloc.lower().replace("www.", "") == DOMAIN:
                    nh = normalize_url(href)
                    if nh != cn and nh not in seen:
                        seen.add(nh)
                        links.append((nh, a.get_text(strip=True) or None))
            
            wc = len(body_text.split())
            ch = compute_content_hash(body_text)
            norm_url = normalize_url(url)
            
            # Insert new post
            row = await conn.fetchrow("""
                INSERT INTO posts (site_id, url, slug, title, body_text, body_html,
                    publish_date, content_hash, word_count, headings, meta_description, http_status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (site_id, url) DO UPDATE SET
                    title=EXCLUDED.title, body_text=EXCLUDED.body_text, body_html=EXCLUDED.body_html,
                    publish_date=COALESCE(EXCLUDED.publish_date, posts.publish_date),
                    content_hash=EXCLUDED.content_hash, word_count=EXCLUDED.word_count,
                    headings=EXCLUDED.headings, meta_description=EXCLUDED.meta_description,
                    http_status=EXCLUDED.http_status, updated_at=NOW()
                RETURNING id
            """, SITE_ID, norm_url, slug, title, body_text, body_html,
                publish_date, ch, wc, hj, meta, resp.status_code)
            
            pid = row["id"]
            
            # Insert links
            if links:
                await conn.executemany(
                    "INSERT INTO internal_links (site_id,source_post_id,target_url,anchor_text) VALUES($1,$2,$3,$4)",
                    [(SITE_ID, pid, h, a) for h, a in links])
            
            stats["ok"] += 1
            del soup, body_html, body_text, links, hds; gc.collect()
            
            if (i+1) % 50 == 0:
                elapsed = time.time() - t0
                log.info("[%d/%d] %.1f/s ok=%d img=%d err=%d skip=%d", i+1, total, (i+1)/elapsed, stats["ok"], stats["img"], stats["err"], stats["skip"])
        
        except Exception as e:
            log.error("[%d] %s: %s", i+1, url[-40:], str(e)[:80])
            stats["err"] += 1
            gc.collect()
    
    client.close()
    
    # Resolve all link targets site-wide
    log.info("Resolving link targets...")
    await conn.execute("UPDATE internal_links il SET target_post_id=p.id FROM posts p WHERE il.site_id=$1 AND p.site_id=$1 AND il.target_url=p.url AND il.target_post_id IS NULL", SITE_ID)
    await conn.execute("UPDATE internal_links il SET target_post_id=p.id FROM posts p WHERE il.site_id=$1 AND p.site_id=$1 AND (il.target_url||'/'=p.url OR il.target_url=p.url||'/') AND il.target_post_id IS NULL", SITE_ID)
    
    elapsed = time.time() - t0
    log.info("DONE in %.0fs (%.1f min)", elapsed, elapsed/60)
    for k,v in stats.items(): log.info("  %s: %s", k, v)
    
    # Final stats
    total_posts = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id=$1", SITE_ID)
    total_links = await conn.fetchval("SELECT count(*) FROM internal_links WHERE source_post_id IN (SELECT id FROM posts WHERE site_id=$1)", SITE_ID)
    resolved = await conn.fetchval("SELECT count(*) FROM internal_links WHERE source_post_id IN (SELECT id FROM posts WHERE site_id=$1) AND target_post_id IS NOT NULL", SITE_ID)
    orphans = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id=$1 AND id NOT IN (SELECT DISTINCT target_post_id FROM internal_links WHERE target_post_id IS NOT NULL)", SITE_ID)
    log.info("FINAL: posts=%d links=%d resolved=%d(%.1f%%) orphans=%d", total_posts, total_links, resolved, resolved*100/total_links if total_links else 0, orphans)
    
    await conn.close()

asyncio.run(main())
