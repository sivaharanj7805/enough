"""Shareable audit report endpoint.

Returns a structured JSON report for a site that can be rendered
as a public shareable page or exported to PDF.

Includes a public PDF audit endpoint (no auth) that accepts URL + email,
enforces a 50-post limit and rate limits (3 per email per day).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db, get_pool
from app.dependencies import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

MAX_AUDIT_POSTS = 50
MAX_AUDITS_PER_EMAIL_PER_DAY = 3


class AuditPDFRequest(BaseModel):
    """Public audit PDF request — no auth required."""
    url: str
    email: EmailStr


class AuditTopPost(BaseModel):
    title: str
    url: str
    health_score: int
    role: str
    issue: str | None = None


class AuditCannPair(BaseModel):
    post_a_title: str
    post_a_url: str
    post_b_title: str
    post_b_url: str
    overlap_score: float
    severity: str
    recommendation: str | None = None


class AuditCluster(BaseModel):
    label: str
    description: str | None
    post_count: int
    health_score: int
    ecosystem_state: str


class AuditRec(BaseModel):
    title: str
    summary: str | None
    rec_type: str
    post_title: str
    post_url: str
    priority: float


class AuditReport(BaseModel):
    site_name: str
    site_domain: str
    total_posts: int
    analyzed_at: str | None
    overall_health: int
    # Counts
    cluster_count: int
    problem_count: int
    rec_count: int
    cann_pair_count: int
    orphan_count: int
    thin_content_count: int
    exact_duplicate_count: int
    # AI Readiness (2026 SEO) — optional, None if scan not yet run
    ai_citability_score: float | None = None
    ai_eeat_score: float | None = None
    ai_schema_score: float | None = None
    ai_extraction_score: float | None = None
    ai_pct_ready: float | None = None
    ai_pct_schema: float | None = None
    # Top findings
    top_clusters: list[AuditCluster]
    top_cann_pairs: list[AuditCannPair]
    top_recs: list[AuditRec]
    worst_posts: list[AuditTopPost]
    best_posts: list[AuditTopPost]
    # Summary text
    headline: str
    key_findings: list[str]


@router.get("/{site_id}/audit-report", response_model=AuditReport)
async def get_audit_report(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Generate a shareable audit report for the site."""
    # Verify ownership
    site = await db.fetchrow(
        "SELECT id, name, domain, last_crawl_at FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if not site:
        raise HTTPException(404, "Site not found")

    data = await _build_audit_data_for_site(db, site_id, dict(site))

    return AuditReport(
        site_name=data["site_name"],
        site_domain=data["site_domain"],
        total_posts=data["total_posts"],
        analyzed_at=data["analyzed_at"],
        overall_health=data["overall_health"],
        cluster_count=data["cluster_count"],
        problem_count=data["problem_count"],
        rec_count=data["rec_count"],
        cann_pair_count=data["cann_pair_count"],
        orphan_count=data["orphan_count"],
        thin_content_count=data["thin_content_count"],
        exact_duplicate_count=data["exact_duplicate_count"],
        ai_citability_score=data["ai_citability_score"],
        ai_eeat_score=data["ai_eeat_score"],
        ai_schema_score=data["ai_schema_score"],
        ai_extraction_score=data["ai_extraction_score"],
        ai_pct_ready=data["ai_pct_ready"],
        ai_pct_schema=data["ai_pct_schema"],
        top_clusters=[AuditCluster(**c) for c in data["top_clusters"]],
        top_cann_pairs=[AuditCannPair(**c) for c in data["top_cann_pairs"]],
        top_recs=[AuditRec(**r) for r in data["top_recs"]],
        worst_posts=[AuditTopPost(**p) for p in data["worst_posts"]],
        best_posts=[AuditTopPost(**p) for p in data["best_posts"]],
        headline=data["headline"],
        key_findings=data["key_findings"],
    )


# ──────────────── Public PDF Audit Endpoint (no auth) ────────────────


async def _build_audit_data_for_site(db: asyncpg.Connection, site_id: UUID, site: dict) -> dict:
    """Build audit report data dict for a site (reusable by PDF + JSON endpoints)."""
    total_posts = await db.fetchval("SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id) or 0
    overall_health = await db.fetchval(
        "SELECT AVG(composite_score) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1",
        site_id,
    ) or 0
    cluster_count = await db.fetchval(
        "SELECT COUNT(*) FROM clusters WHERE site_id = $1 AND parent_cluster_id IS NULL", site_id
    ) or 0
    problem_count = await db.fetchval(
        "SELECT COUNT(*) FROM content_problems cp JOIN posts p ON p.id = cp.post_id WHERE p.site_id = $1",
        site_id,
    ) or 0
    rec_count = await db.fetchval("SELECT COUNT(*) FROM recommendations WHERE site_id = $1", site_id) or 0
    cann_pair_count = await db.fetchval(
        "SELECT COUNT(*) FROM cannibalization_pairs cp JOIN clusters cl ON cl.id = cp.cluster_id WHERE cl.site_id = $1",
        site_id,
    ) or 0
    orphan_count = await db.fetchval(
        "SELECT COUNT(*) FROM content_problems cp JOIN posts p ON p.id = cp.post_id "
        "WHERE p.site_id = $1 AND cp.problem_type = 'orphan'",
        site_id,
    ) or 0
    thin_count = await db.fetchval(
        "SELECT COUNT(*) FROM content_problems cp JOIN posts p ON p.id = cp.post_id "
        "WHERE p.site_id = $1 AND cp.problem_type = 'thin_content'",
        site_id,
    ) or 0
    exact_dup_count = await db.fetchval(
        "SELECT COUNT(*) FROM cannibalization_pairs cp JOIN clusters cl ON cl.id = cp.cluster_id "
        "WHERE cl.site_id = $1 AND cp.cosine_similarity >= 0.99",
        site_id,
    ) or 0

    # Top clusters (by health score)
    cluster_rows = await db.fetch(
        """SELECT label, description, post_count, health_score, ecosystem_state
           FROM clusters WHERE site_id = $1
           ORDER BY health_score DESC NULLS LAST LIMIT 6""",
        site_id,
    )
    top_clusters = [
        {"label": r["label"] or "Unnamed Cluster", "description": r["description"],
         "post_count": r["post_count"] or 0, "health_score": round(r["health_score"] or 0),
         "ecosystem_state": r["ecosystem_state"] or "seedbed"}
        for r in cluster_rows
    ]

    # Top cann pairs
    cann_rows = await db.fetch(
        """SELECT pa.title AS a_title, pa.url AS a_url,
                  pb.title AS b_title, pb.url AS b_url,
                  cp.cosine_similarity, cp.severity,
                  r.title AS rec_title
           FROM cannibalization_pairs cp
           JOIN clusters cl ON cl.id = cp.cluster_id
           JOIN posts pa ON pa.id = cp.post_a_id
           JOIN posts pb ON pb.id = cp.post_b_id
           LEFT JOIN recommendations r ON r.post_id = cp.post_a_id AND r.site_id = cl.site_id
               AND r.recommendation_type IN ('merge', 'differentiate', 'redirect')
           WHERE cl.site_id = $1
           ORDER BY cp.cosine_similarity DESC
           LIMIT 8""",
        site_id,
    )
    top_cann_pairs = [
        {"post_a_title": r["a_title"] or "", "post_a_url": r["a_url"] or "",
         "post_b_title": r["b_title"] or "", "post_b_url": r["b_url"] or "",
         "overlap_score": round(r["cosine_similarity"] or 0, 3),
         "severity": r["severity"] or "medium", "recommendation": r["rec_title"]}
        for r in cann_rows
    ]

    # Top recommendations
    rec_rows = await db.fetch(
        """SELECT r.title, r.summary, r.recommendation_type, r.priority,
                  p.title AS post_title, p.url AS post_url
           FROM recommendations r
           JOIN posts p ON p.id = r.post_id
           WHERE r.site_id = $1
           ORDER BY CASE r.priority WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC
           LIMIT 8""",
        site_id,
    )
    top_recs = [
        {"title": r["title"] or "", "summary": r["summary"],
         "rec_type": r["recommendation_type"] or "",
         "post_title": r["post_title"] or "", "post_url": r["post_url"] or "",
         "priority": {'critical': 4.0, 'high': 3.0, 'medium': 2.0, 'low': 1.0}.get(r["priority"] or 'low', 1.0)}
        for r in rec_rows
    ]

    # Worst posts
    worst_rows = await db.fetch(
        """SELECT p.title, p.url, phs.composite_score, phs.role, cp.problem_type
           FROM posts p
           JOIN post_health_scores phs ON phs.post_id = p.id
           LEFT JOIN content_problems cp ON cp.post_id = p.id
           WHERE p.site_id = $1
           ORDER BY phs.composite_score ASC NULLS LAST
           LIMIT 5""",
        site_id,
    )
    worst_posts = [
        {"title": r["title"] or "", "url": r["url"] or "",
         "health_score": round(r["composite_score"] or 0),
         "role": r["role"] or "dead_weight", "issue": r["problem_type"]}
        for r in worst_rows
    ]

    # Best posts (highest health, pillar only)
    best_rows = await db.fetch(
        """SELECT p.title, p.url, phs.composite_score, phs.role
           FROM posts p
           JOIN post_health_scores phs ON phs.post_id = p.id
           WHERE p.site_id = $1 AND phs.role = 'pillar'
           ORDER BY phs.composite_score DESC
           LIMIT 5""",
        site_id,
    )
    best_posts = [
        {"title": r["title"] or "", "url": r["url"] or "",
         "health_score": round(r["composite_score"] or 0),
         "role": r["role"] or "pillar"}
        for r in best_rows
    ]

    # AI Readiness scores (optional — None if scan not yet run)
    ai_row = await db.fetchrow(
        """
        SELECT
            ROUND(AVG(ai_citability_score)::numeric, 1) AS avg_cite,
            ROUND(AVG(eeat_score)::numeric, 1) AS avg_eeat,
            ROUND(AVG(schema_score)::numeric, 1) AS avg_schema,
            ROUND(AVG(extraction_score)::numeric, 1) AS avg_extract,
            ROUND(COUNT(*) FILTER (WHERE ai_citability_score >= 60)::numeric /
                  NULLIF(COUNT(*) FILTER (WHERE ai_citability_score IS NOT NULL), 0) * 100, 1) AS pct_ready,
            ROUND(COUNT(*) FILTER (WHERE schema_score > 0)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 1) AS pct_schema
        FROM post_health_scores phs
        JOIN posts p ON p.id = phs.post_id
        WHERE p.site_id = $1 AND ai_citability_score IS NOT NULL
        """,
        site_id,
    )
    ai_cite = float(ai_row["avg_cite"]) if ai_row and ai_row["avg_cite"] is not None else None
    ai_eeat = float(ai_row["avg_eeat"]) if ai_row and ai_row["avg_eeat"] is not None else None
    ai_schema = float(ai_row["avg_schema"]) if ai_row and ai_row["avg_schema"] is not None else None
    ai_extract = float(ai_row["avg_extract"]) if ai_row and ai_row["avg_extract"] is not None else None
    ai_pct_ready = float(ai_row["pct_ready"]) if ai_row and ai_row["pct_ready"] is not None else None
    ai_pct_schema = float(ai_row["pct_schema"]) if ai_row and ai_row["pct_schema"] is not None else None

    # Key findings
    key_findings: list[str] = []
    if cann_pair_count > 0:
        key_findings.append(f"{cann_pair_count} posts are cannibalizing each other for the same keywords")
    if exact_dup_count > 0:
        key_findings.append(f"{exact_dup_count} near-exact duplicate URL pairs detected")
    if orphan_count > 0:
        key_findings.append(f"{orphan_count} orphan posts have no inbound internal links")
    if thin_count > 0:
        key_findings.append(f"{thin_count} posts are too thin relative to cluster average")
    if overall_health < 40:
        key_findings.append(f"Overall content health is {round(overall_health)}/100 — significant optimization opportunity")
    elif overall_health >= 65:
        key_findings.append(f"Content health is {round(overall_health)}/100 — above average with targeted improvement opportunities")

    # AI readiness key findings
    if ai_cite is not None:
        if ai_cite < 40:
            key_findings.append(f"Only {ai_pct_ready}% of posts are AI-citable — content lacks data tables, original stats, and experience markers that AI systems prefer to cite")
        if ai_pct_schema is not None and ai_pct_schema < 30:
            key_findings.append(f"{100 - ai_pct_schema:.0f}% of posts have no schema markup — missing Article/FAQ JSON-LD that dramatically increases AI Overview citations")

    # Headline
    if cann_pair_count >= 50:
        headline = f"Found {cann_pair_count} cannibalizing post pairs across {cluster_count} topic clusters"
    elif rec_count >= 100:
        headline = f"Generated {rec_count} specific recommendations across {total_posts} posts"
    else:
        headline = f"Analyzed {total_posts} posts across {cluster_count} topic clusters — {problem_count} issues detected"

    return {
        "site_name": site.get("name") or site.get("domain", ""),
        "site_domain": site.get("domain", ""),
        "total_posts": int(total_posts),
        "analyzed_at": str(site.get("last_crawl_at")) if site.get("last_crawl_at") else None,
        "overall_health": round(overall_health),
        "cluster_count": int(cluster_count),
        "problem_count": int(problem_count),
        "rec_count": int(rec_count),
        "cann_pair_count": int(cann_pair_count),
        "orphan_count": int(orphan_count),
        "thin_content_count": int(thin_count),
        "exact_duplicate_count": int(exact_dup_count),
        "ai_citability_score": ai_cite,
        "ai_eeat_score": ai_eeat,
        "ai_schema_score": ai_schema,
        "ai_extraction_score": ai_extract,
        "ai_pct_ready": ai_pct_ready,
        "ai_pct_schema": ai_pct_schema,
        "top_clusters": top_clusters,
        "top_cann_pairs": top_cann_pairs,
        "top_recs": top_recs,
        "worst_posts": worst_posts,
        "best_posts": best_posts,
        "key_findings": key_findings,
        "headline": headline,
    }


@router.post("/audit-report/pdf")
@limiter.limit("6/minute")
async def generate_audit_pdf_endpoint(
    request: Request,
    body: AuditPDFRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Public PDF audit endpoint — no auth required.

    Accepts a blog URL + email, generates a PDF audit report.
    Enforces:
    - 50 post limit per audit
    - 3 audits per email per day rate limit
    """
    # Rate limit: 3 per email per day
    today = datetime.now(timezone.utc).date()
    audit_count = await db.fetchval(
        """SELECT COUNT(*) FROM audit_requests
           WHERE email = $1 AND created_at::date = $2""",
        body.email, today,
    )
    if (audit_count or 0) >= MAX_AUDITS_PER_EMAIL_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: maximum {MAX_AUDITS_PER_EMAIL_PER_DAY} audit reports per email per day.",
        )

    # Find the site by domain (extract domain from URL)
    from urllib.parse import urlparse
    parsed = urlparse(body.url if "://" in body.url else f"https://{body.url}")
    domain = parsed.netloc or parsed.path
    domain = domain.replace("www.", "").strip("/")

    if not domain:
        raise HTTPException(400, "Invalid URL")

    site = await db.fetchrow(
        "SELECT id, name, domain, last_crawl_at FROM sites WHERE domain ILIKE $1 LIMIT 1",
        f"%{domain}%",
    )
    if not site:
        # Check if there's already a pending pipeline for this email
        pending = await db.fetchval(
            "SELECT id FROM pending_audit_pipelines WHERE email = $1 AND status IN ('pending', 'running')",
            body.email,
        )
        if pending:
            return JSONResponse(
                status_code=202,
                content={"message": f"Your analysis of {domain} is already running. Check your inbox within 25 minutes.", "domain": domain},
            )

        # Create anonymous site (user_id = NULL)
        site_row = await db.fetchrow(
            """INSERT INTO sites (domain, name, cms_type)
               VALUES ($1, $2, 'sitemap')
               RETURNING id, domain, name, last_crawl_at""",
            domain, domain,
        )
        site_id = site_row["id"]

        # Track pending pipeline
        await db.execute(
            "INSERT INTO pending_audit_pipelines (email, domain, site_id) VALUES ($1, $2, $3)",
            body.email, domain, site_id,
        )

        # Record audit request
        await db.execute(
            "INSERT INTO audit_requests (email, domain, site_id, created_at) VALUES ($1, $2, $3, $4)",
            body.email, domain, site_id, datetime.now(timezone.utc),
        )

        # Run pipeline in background, email PDF on completion
        background_tasks.add_task(
            _run_audit_pipeline_and_email, site_id, body.email, domain,
        )

        return JSONResponse(
            status_code=202,
            content={
                "message": f"We're analyzing {domain} now. Your audit report will arrive at {body.email} within 25 minutes.",
                "domain": domain,
                "email": body.email,
            },
        )

    site_id = site["id"]

    # Enforce 50 post limit
    total_posts = await db.fetchval("SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id) or 0
    if total_posts > MAX_AUDIT_POSTS:
        logger.info(
            "Audit PDF for %s: capping display at %d posts (site has %d)",
            domain, MAX_AUDIT_POSTS, total_posts,
        )

    # Record the audit request
    await db.execute(
        """INSERT INTO audit_requests (email, domain, site_id, created_at)
           VALUES ($1, $2, $3, $4)""",
        body.email, domain, site_id, datetime.now(timezone.utc),
    )

    # Build audit data and generate PDF
    audit_data = await _build_audit_data_for_site(db, site_id, dict(site))

    from app.services.pdf_report import generate_audit_pdf
    pdf_bytes = generate_audit_pdf(audit_data)

    # Schedule drip email sequence in background
    background_tasks.add_task(
        _schedule_drip_sequence, body.email, domain, site_id, audit_data, pdf_bytes,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="enough-audit-{domain}.pdf"',
        },
    )


async def _schedule_drip_sequence(
    email: str, domain: str, site_id: UUID, audit_data: dict, pdf_bytes: bytes,
) -> None:
    """Schedule the 3-email drip sequence for an audit lead."""
    try:
        from app.services.drip_sequence import DripSequenceService
        pool = await get_pool()
        async with pool.acquire() as db:
            service = DripSequenceService()
            await service.schedule_drip(db, email, domain, site_id, audit_data, pdf_bytes)
    except Exception as e:
        logger.error("Failed to schedule drip for %s: %s", email, e)


async def _run_audit_pipeline_and_email(
    site_id: UUID, email: str, domain: str,
) -> None:
    """Run full ingestion pipeline for an anonymous audit site, then email the PDF.

    Uses the 10-step _run_full_pipeline from ingestion.py (includes crawl,
    embeddings, readability, pagerank, intent, clustering, health, cannibalization,
    problems, recommendations, and AI citability) — NOT the 5-step intelligence
    version which skips crawl/embeddings/readability/pagerank/intent.
    """
    from app.routers.ingestion import _run_full_pipeline

    pool = await get_pool()

    try:
        # Update pipeline status
        async with pool.acquire() as db:
            await db.execute(
                "UPDATE pending_audit_pipelines SET status = 'running' WHERE site_id = $1",
                site_id,
            )

        # Build site dict needed by _run_full_pipeline
        async with pool.acquire() as db:
            site = await db.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)

        # Run the full 10-step pipeline (crawl → embed → readability → pagerank →
        # intent → cluster → health → cannibalization → problems → recs → AI citability)
        await _run_full_pipeline(site_id, dict(site))

        # Verify pipeline succeeded
        async with pool.acquire() as db:
            crawl = await db.fetchrow(
                "SELECT status FROM crawl_jobs WHERE site_id = $1", site_id,
            )
            if crawl and crawl["status"] == "failed":
                raise ValueError(f"Pipeline failed for {domain}")

        # Generate PDF and email it
        async with pool.acquire() as db:
            site = await db.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
            audit_data = await _build_audit_data_for_site(db, site_id, dict(site))

            from app.services.pdf_report import generate_audit_pdf
            pdf_bytes = generate_audit_pdf(audit_data)

            # Schedule full drip sequence (checks email_optouts internally)
            await _schedule_drip_sequence(email, domain, site_id, audit_data, pdf_bytes)

            # Mark pipeline complete
            await db.execute(
                "UPDATE pending_audit_pipelines SET status = 'completed', completed_at = NOW() WHERE site_id = $1",
                site_id,
            )

        logger.info("Audit pipeline completed for %s, PDF emailed to %s", domain, email)

    except Exception as e:
        logger.error("Audit pipeline failed for %s: %s", domain, e)
        try:
            async with pool.acquire() as db:
                await db.execute(
                    "UPDATE pending_audit_pipelines SET status = 'failed', error = $1 WHERE site_id = $2",
                    str(e)[:500], site_id,
                )
        except Exception:
            pass


@router.post("/admin/generate-audit")
async def admin_generate_audit(
    request: Request,
    body: AuditPDFRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Admin-only endpoint to manually trigger an audit for any domain.

    Requires X-Admin-Secret header matching ADMIN_SECRET env var.
    """
    from app.config import get_settings
    settings = get_settings()

    admin_secret = getattr(settings, 'admin_secret', None) or settings.cron_secret
    provided = request.headers.get("X-Admin-Secret", "")

    if not admin_secret or not provided:
        raise HTTPException(401, "Missing admin secret")

    import hmac
    if not hmac.compare_digest(provided, admin_secret):
        raise HTTPException(403, "Invalid admin secret")

    # Reuse the same cold-start flow
    from urllib.parse import urlparse
    parsed = urlparse(body.url if "://" in body.url else f"https://{body.url}")
    domain = parsed.netloc or parsed.path
    domain = domain.replace("www.", "").strip("/")

    if not domain:
        raise HTTPException(400, "Invalid URL")

    # Check if site already exists
    site = await db.fetchrow(
        "SELECT id, name, domain, last_crawl_at FROM sites WHERE domain ILIKE $1 LIMIT 1",
        f"%{domain}%",
    )

    if site:
        # Site exists — just generate PDF and email
        audit_data = await _build_audit_data_for_site(db, site["id"], dict(site))
        from app.services.pdf_report import generate_audit_pdf
        pdf_bytes = generate_audit_pdf(audit_data)
        background_tasks.add_task(
            _schedule_drip_sequence, body.email, domain, site["id"], audit_data, pdf_bytes,
        )
        return {"message": f"PDF generated for existing site {domain}, drip scheduled for {body.email}", "site_id": str(site["id"])}

    # New domain — create and run pipeline
    site_row = await db.fetchrow(
        "INSERT INTO sites (domain, name, cms_type) VALUES ($1, $2, 'sitemap') RETURNING id",
        domain, domain,
    )
    await db.execute(
        "INSERT INTO pending_audit_pipelines (email, domain, site_id) VALUES ($1, $2, $3)",
        body.email, domain, site_row["id"],
    )
    background_tasks.add_task(
        _run_audit_pipeline_and_email, site_row["id"], body.email, domain,
    )
    return {"message": f"Pipeline started for {domain}, PDF will be emailed to {body.email}", "site_id": str(site_row["id"])}


# ──────────────── Social Proof Stats (public, no auth) ────────────────


@router.get("/audit-report/stats")
async def get_audit_stats(
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Public endpoint returning aggregate stats for landing page social proof.

    Returns counts of blogs analyzed, cannibalization pairs found, and posts analyzed.
    Cached at the HTTP level — call infrequently.
    """
    blogs = await db.fetchval("SELECT COUNT(*) FROM sites") or 0
    posts = await db.fetchval("SELECT COUNT(*) FROM posts") or 0
    cann_pairs = await db.fetchval("SELECT COUNT(*) FROM cannibalization_pairs") or 0

    return {
        "blogs_analyzed": blogs,
        "posts_analyzed": posts,
        "cann_pairs_found": cann_pairs,
    }
