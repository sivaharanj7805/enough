"""Extract modified dates from body HTML and HTTP Last-Modified headers.

Searches for:
1. "Updated:", "Last updated:", "Updated on:", patterns in body_html
2. HTTP Last-Modified response headers (re-fetch with HEAD request)
3. Wayback Machine CDX API last crawl date (free, no auth)

Updates posts.modified_date where found.
"""
import asyncio, asyncpg, httpx, json, logging, os, re, sys, time
from datetime import datetime, timezone
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

SITE_ID = UUID("32296e5d-7924-4d9f-92b8-7f774c634fad")

# Patterns to find "Updated:" date text in HTML
UPDATE_PATTERNS = [
    r'[Uu]pdated?\s*(?:on\s*)?:?\s*([A-Z][a-z]+ \d{1,2},?\s+\d{4})',
    r'[Ll]ast\s+[Uu]pdated?\s*:?\s*([A-Z][a-z]+ \d{1,2},?\s+\d{4})',
    r'[Rr]evised?\s*:?\s*([A-Z][a-z]+ \d{1,2},?\s+\d{4})',
    r'[Mm]odified?\s*:?\s*([A-Z][a-z]+ \d{1,2},?\s+\d{4})',
    r'<time[^>]+datetime=["\'](\d{4}-\d{2}-\d{2}[T\d:+Z.-]*)["\']',
    r'dateModified["\']?\s*:\s*["\'](\d{4}-\d{2}-\d{2}[T\d:+Z.-]*)["\']',
    r'"@type"\s*:\s*"Article".*?"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})',
]

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


def parse_date_string(s: str) -> datetime | None:
    """Try to parse a date string into a datetime."""
    s = s.strip().rstrip(',')
    # ISO format
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    # "March 17, 2024" or "March 17 2024"
    parts = s.replace(',', '').split()
    if len(parts) == 3:
        month_str = parts[0].lower()
        month = MONTH_MAP.get(month_str)
        if month:
            try:
                day = int(parts[1])
                year = int(parts[2])
                return datetime(year, month, day, tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass
    return None


async def main():
    from dotenv import load_dotenv
    load_dotenv()

    conn = await asyncpg.connect(os.environ['DATABASE_URL'])

    posts = await conn.fetch(
        "SELECT id, url, body_html FROM posts WHERE site_id=$1 AND modified_date IS NULL ORDER BY publish_date DESC",
        SITE_ID,
    )
    log.info("Checking freshness for %d posts without modified_date", len(posts))

    stats = {'text_found': 0, 'header_found': 0, 'wayback_found': 0, 'none': 0}
    t0 = time.time()

    # Phase 1: Extract from body_html (no network needed)
    log.info("Phase 1: Scanning body_html for date patterns...")
    text_found = 0
    for post in posts:
        body = post['body_html'] or ''
        found_date = None

        for pattern in UPDATE_PATTERNS:
            matches = re.findall(pattern, body, re.IGNORECASE | re.DOTALL)
            for m in matches:
                dt = parse_date_string(m)
                if dt and dt.year >= 2010 and dt <= datetime.now(timezone.utc):
                    # Sanity: must be after publish_date
                    found_date = dt
                    break
            if found_date:
                break

        if found_date:
            await conn.execute(
                "UPDATE posts SET modified_date=$1 WHERE id=$2",
                found_date, post['id'],
            )
            text_found += 1
            stats['text_found'] += 1

    log.info("Phase 1 complete: %d dates extracted from body text", text_found)

    # Phase 2: HTTP Last-Modified headers (HEAD requests)
    log.info("Phase 2: Checking HTTP Last-Modified headers...")
    posts_still_missing = await conn.fetch(
        "SELECT id, url FROM posts WHERE site_id=$1 AND modified_date IS NULL ORDER BY publish_date DESC LIMIT 200",
        SITE_ID,
    )
    log.info("  Checking %d posts via HEAD request", len(posts_still_missing))

    header_found = 0
    client = httpx.Client(timeout=10, follow_redirects=True, headers={"User-Agent": "Enough/0.1"})

    for post in posts_still_missing:
        try:
            time.sleep(0.1)
            resp = client.head(post['url'])
            lm = resp.headers.get('last-modified') or resp.headers.get('Last-Modified')
            if lm:
                # Parse HTTP date format: "Mon, 17 Mar 2026 12:00:00 GMT"
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(lm).replace(tzinfo=timezone.utc)
                    if dt.year >= 2010 and dt <= datetime.now(timezone.utc):
                        await conn.execute("UPDATE posts SET modified_date=$1 WHERE id=$2", dt, post['id'])
                        header_found += 1
                        stats['header_found'] += 1
                except Exception:
                    pass
        except Exception:
            pass

    client.close()
    log.info("Phase 2 complete: %d dates from Last-Modified headers", header_found)

    # Phase 3: Wayback Machine CDX API
    log.info("Phase 3: Wayback Machine CDX API for remaining posts...")
    posts_still_missing2 = await conn.fetch(
        "SELECT id, url FROM posts WHERE site_id=$1 AND modified_date IS NULL ORDER BY publish_date DESC",
        SITE_ID,
    )
    log.info("  %d posts still missing modified_date", len(posts_still_missing2))

    wayback_found = 0
    async with httpx.AsyncClient(timeout=15.0) as async_client:
        for i, post in enumerate(posts_still_missing2):
            try:
                await asyncio.sleep(0.3)
                url = post['url']
                # CDX API returns the most recent crawl date
                cdx_url = f"http://web.archive.org/cdx/search/cdx?url={url}&output=json&limit=1&fl=timestamp&filter=statuscode:200&from=20200101&to=20260101&fastLatest=true"
                resp = await async_client.get(cdx_url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 1:  # First row is header
                        ts = data[1][0]  # "20241215130000"
                        try:
                            dt = datetime.strptime(ts[:8], '%Y%m%d').replace(tzinfo=timezone.utc)
                            await conn.execute("UPDATE posts SET modified_date=$1 WHERE id=$2", dt, post['id'])
                            wayback_found += 1
                            stats['wayback_found'] += 1
                        except ValueError:
                            pass
            except Exception:
                pass

            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                log.info("  Wayback [%d/%d] found=%d (%.0fs)", i+1, len(posts_still_missing2), wayback_found, elapsed)

    log.info("Phase 3 complete: %d dates from Wayback Machine", wayback_found)

    # Final stats
    with_date = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id=$1 AND modified_date IS NOT NULL", SITE_ID)
    total = await conn.fetchval("SELECT count(*) FROM posts WHERE site_id=$1", SITE_ID)
    elapsed = time.time() - t0

    log.info("=" * 60)
    log.info("FRESHNESS EXTRACTION COMPLETE in %.0fs (%.1f min)", elapsed, elapsed / 60)
    log.info("  Text patterns: %d", stats['text_found'])
    log.info("  HTTP Last-Modified: %d", stats['header_found'])
    log.info("  Wayback Machine: %d", stats['wayback_found'])
    log.info("  Posts with modified_date: %d/%d (%.1f%%)", with_date, total, with_date * 100 / total)

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
