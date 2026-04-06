"""Competitive AI readiness benchmarking.

Crawls a competitor's blog, scores each post with the same AI citability functions,
and returns a head-to-head comparison with the user's site.
"""

import logging
from uuid import UUID

import asyncpg

from app.services.ai_citability import (
    compute_citability_score,
    compute_eeat_score,
    compute_extraction_score,
    compute_schema_score,
)
from app.services.sitemap import SitemapCrawler
from app.utils.ssrf_protection import validate_domain_not_internal

logger = logging.getLogger(__name__)


async def benchmark_competitor(
    db: asyncpg.Connection,
    site_id: UUID,
    competitor_domain: str,
    max_pages: int = 50,
) -> dict:
    """Crawl a competitor domain and compare AI readiness scores.

    Returns a comparison dict with our scores, their scores, and gaps.
    Caps at max_pages to keep cost/time reasonable.
    """
    # SSRF protection: reject internal/private domains
    validate_domain_not_internal(competitor_domain, "competitor_domain")

    logger.info("Benchmarking competitor %s for site %s (max %d pages)", competitor_domain, site_id, max_pages)

    # 1. Crawl competitor
    crawler = SitemapCrawler(
        sitemap_url=f"https://{competitor_domain}/sitemap.xml",
        domain=competitor_domain,
        max_pages=max_pages,
        concurrency=10,
        max_retries=2,
        timeout_seconds=20.0,
    )
    try:
        posts = await crawler.crawl()
    except Exception as e:
        logger.error("Failed to crawl competitor %s: %s", competitor_domain, e)
        return {"error": f"Failed to crawl {competitor_domain}: {str(e)[:200]}"}

    if not posts:
        return {"error": f"No content found on {competitor_domain}"}

    logger.info("Crawled %d posts from %s", len(posts), competitor_domain)

    # 2. Score each competitor post
    competitor_scores: list[dict[str, float]] = []
    for post in posts:
        if not post.body_text or len(post.body_text) < 50:
            continue
        try:
            cite, _ = compute_citability_score(post.body_text, post.body_html)
            eeat, _ = compute_eeat_score(post.body_html)
            schema, _ = compute_schema_score(post.body_html)
            extract, _ = compute_extraction_score(post.body_text, post.body_html, post.headings)
            competitor_scores.append({
                "citability": cite, "eeat": eeat,
                "schema": schema, "extraction": extract,
            })
        except Exception as e:
            logger.debug("Scoring failed for %s: %s", post.url, e)

    if not competitor_scores:
        return {"error": f"Could not score any posts from {competitor_domain}"}

    # 3. Compute competitor averages
    n = len(competitor_scores)
    comp_avg = {
        "citability": round(sum(s["citability"] for s in competitor_scores) / n, 1),
        "eeat": round(sum(s["eeat"] for s in competitor_scores) / n, 1),
        "schema": round(sum(s["schema"] for s in competitor_scores) / n, 1),
        "extraction": round(sum(s["extraction"] for s in competitor_scores) / n, 1),
    }
    comp_ai_ready_pct = round(
        sum(1 for s in competitor_scores if s["citability"] >= 60) / n * 100, 1
    )

    # 4. Get our site's scores
    our_row = await db.fetchrow(
        """
        SELECT ROUND(AVG(ai_citability_score)::numeric, 1) AS cite,
               ROUND(AVG(eeat_score)::numeric, 1) AS eeat,
               ROUND(AVG(schema_score)::numeric, 1) AS schema,
               ROUND(AVG(extraction_score)::numeric, 1) AS extract,
               ROUND(COUNT(*) FILTER (WHERE ai_citability_score >= 60)::numeric /
                     NULLIF(COUNT(*) FILTER (WHERE ai_citability_score IS NOT NULL), 0) * 100, 1) AS pct_ready
        FROM post_health_scores phs
        JOIN posts p ON p.id = phs.post_id
        WHERE p.site_id = $1 AND ai_citability_score IS NOT NULL
        """,
        site_id,
    )

    our_scores = {
        "citability": float(our_row["cite"]) if our_row and our_row["cite"] else 0,
        "eeat": float(our_row["eeat"]) if our_row and our_row["eeat"] else 0,
        "schema": float(our_row["schema"]) if our_row and our_row["schema"] else 0,
        "extraction": float(our_row["extract"]) if our_row and our_row["extract"] else 0,
    }
    our_pct_ready = float(our_row["pct_ready"]) if our_row and our_row["pct_ready"] else 0

    # 5. Compute gaps
    gaps = {k: round(comp_avg[k] - our_scores[k], 1) for k in comp_avg}

    # 6. Generate insights
    insights: list[str] = []
    if gaps["schema"] > 20:
        insights.append(f"Competitor has {comp_avg['schema']:.0f}/100 schema score vs your {our_scores['schema']:.0f}. Add Article/FAQ JSON-LD to close the gap.")
    if gaps["eeat"] > 20:
        insights.append(f"Competitor's E-E-A-T score is {gaps['eeat']:.0f} points higher. Add author bios, dates, and credentials.")
    if gaps["citability"] > 15:
        insights.append(f"Competitor content is more AI-citable ({comp_avg['citability']:.0f} vs {our_scores['citability']:.0f}). Add data tables, stats, and experience markers.")
    if comp_ai_ready_pct > our_pct_ready + 15:
        insights.append(f"{comp_ai_ready_pct:.0f}% of competitor posts are AI-ready vs your {our_pct_ready:.0f}%.")

    if not insights:
        if all(g <= 0 for g in gaps.values()):
            insights.append("You outperform this competitor on AI readiness across all dimensions.")
        else:
            insights.append("Your AI readiness is comparable to this competitor.")

    # 7. Store benchmark in competitor_sites if table exists
    try:
        await db.execute(
            """INSERT INTO competitor_sites (site_id, domain, post_count, status)
               VALUES ($1, $2, $3, 'crawled')
               ON CONFLICT (site_id, domain) DO UPDATE SET
                   post_count = EXCLUDED.post_count, status = 'crawled', last_crawled_at = NOW()""",
            site_id, competitor_domain, len(posts),
        )
    except Exception:
        pass  # Table might not exist or have different schema

    logger.info(
        "Benchmark complete: %s (%d posts) vs site %s — gaps: %s",
        competitor_domain, n, site_id, gaps,
    )

    return {
        "competitor_domain": competitor_domain,
        "competitor_posts_analyzed": n,
        "our_scores": our_scores,
        "our_pct_ready": our_pct_ready,
        "competitor_scores": comp_avg,
        "competitor_pct_ready": comp_ai_ready_pct,
        "gaps": gaps,
        "insights": insights,
    }
