"""Prospect discovery and outreach automation.

Discovers blog domains, finds contact emails, runs audit pipelines,
and triggers drip email sequences. Reuses the existing cold-start
pipeline and drip infrastructure.
"""

import logging
import re
from uuid import UUID

import asyncpg
import httpx

from app.utils.ssrf_protection import validate_domain_not_internal

logger = logging.getLogger(__name__)


async def discover_prospects_manual(
    db: asyncpg.Connection,
    domains: list[str],
    niche: str = "",
) -> int:
    """Insert prospect records for a list of manually provided domains.

    Skips domains that already exist. Returns count of new prospects created.
    """
    created = 0
    for domain in domains:
        domain = domain.strip().lower().replace("https://", "").replace("http://", "").replace("www.", "").strip("/")
        if not domain or len(domain) > 253:
            continue
        # SSRF protection: skip internal/private domains
        try:
            validate_domain_not_internal(domain, "prospect_domain")
        except ValueError:
            logger.warning("Skipping internal domain prospect: %s", domain)
            continue
        try:
            await db.execute(
                """INSERT INTO prospects (domain, niche, source)
                   VALUES ($1, $2, 'manual')
                   ON CONFLICT (domain) DO NOTHING""",
                domain, niche,
            )
            created += 1
        except Exception as e:
            logger.debug("Failed to insert prospect %s: %s", domain, e)

    logger.info("Created %d prospects from %d domains (niche: %s)", created, len(domains), niche)
    return created


async def discover_prospects_google(
    db: asyncpg.Connection,
    keyword: str,
    max_results: int = 30,
) -> int:
    """Use Google Custom Search API to find blog domains for a niche keyword.

    Requires GOOGLE_CSE_KEY and GOOGLE_CSE_ID in config.
    Returns count of new prospects discovered.
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.google_cse_key or not settings.google_cse_id:
        logger.warning("Google CSE not configured — set GOOGLE_CSE_KEY and GOOGLE_CSE_ID")
        return 0

    discovered: list[str] = []
    # Google CSE returns max 10 per request, paginate with start parameter
    for start in range(1, max_results + 1, 10):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": settings.google_cse_key,
                        "cx": settings.google_cse_id,
                        "q": f"{keyword} blog",
                        "num": min(10, max_results - len(discovered)),
                        "start": start,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data.get("items", []):
                    url = item.get("link", "")
                    if url:
                        from urllib.parse import urlparse
                        domain = urlparse(url).netloc.replace("www.", "")
                        if domain and domain not in discovered:
                            discovered.append(domain)
        except Exception as e:
            logger.warning("Google CSE search failed (page %d): %s", start, e)
            break

    if not discovered:
        return 0

    # Create discovery job record
    job_id = await db.fetchval(
        """INSERT INTO discovery_jobs (niche_keyword, source, status, domains_found, started_at, completed_at)
           VALUES ($1, 'google_cse', 'completed', $2, NOW(), NOW())
           RETURNING id""",
        keyword, len(discovered),
    )

    # Insert prospects
    return await discover_prospects_manual(db, discovered, niche=keyword)


async def find_contact_email(domain: str) -> str | None:
    """Scrape /about and /contact pages for email addresses.

    Filters out generic addresses (noreply@, support@, info@).
    Returns the most likely human contact email, or None.
    """
    email_pattern = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    generic_prefixes = {"noreply", "no-reply", "support", "info", "hello", "contact", "admin", "webmaster", "help"}

    # SSRF protection: reject internal/private domains
    validate_domain_not_internal(domain, "prospect_domain")

    found_emails: list[str] = []
    pages_to_check = [
        f"https://{domain}/about",
        f"https://{domain}/about/",
        f"https://{domain}/contact",
        f"https://{domain}/contact/",
        f"https://{domain}/team",
        f"https://{domain}/",
    ]

    async with httpx.AsyncClient(
        timeout=10.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Tended/1.0)"},
    ) as client:
        for url in pages_to_check:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                emails = email_pattern.findall(resp.text)
                for email in emails:
                    email = email.lower()
                    prefix = email.split("@")[0]
                    # Skip generic, image files, and the domain's own generic addresses
                    if prefix not in generic_prefixes and not email.endswith((".png", ".jpg", ".gif", ".svg")):
                        found_emails.append(email)
            except Exception:
                continue

    if not found_emails:
        return None

    # Prefer emails at the same domain, then any email
    domain_emails = [e for e in found_emails if domain in e]
    return domain_emails[0] if domain_emails else found_emails[0]


async def run_prospect_audit(
    db: asyncpg.Connection,
    prospect_id: UUID,
) -> dict:
    """Run the full audit pipeline for a prospect domain and schedule outreach.

    Reuses the existing cold-start pipeline from audit_report.py.
    """
    prospect = await db.fetchrow("SELECT * FROM prospects WHERE id = $1", prospect_id)
    if not prospect:
        return {"error": "Prospect not found"}

    domain = prospect["domain"]
    email = prospect["contact_email"]

    # Update status
    await db.execute("UPDATE prospects SET status = 'auditing' WHERE id = $1", prospect_id)

    try:
        # Create anonymous site (reuse audit_report.py pattern)
        site_row = await db.fetchrow(
            """INSERT INTO sites (domain, name, cms_type)
               VALUES ($1, $2, 'sitemap')
               ON CONFLICT (domain) DO UPDATE SET updated_at = NOW()
               RETURNING id""",
            domain, domain,
        )
        site_id = site_row["id"]

        # Update prospect with site_id
        await db.execute("UPDATE prospects SET site_id = $1 WHERE id = $2", site_id, prospect_id)

        # Run the full pipeline — skip chunk confirmation ($0.50) for cold outreach
        from app.routers.ingestion import _run_full_pipeline
        site = await db.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
        await _run_full_pipeline(site_id, dict(site), skip_chunk_confirmation=True)

        # Get the health score
        avg_health = await db.fetchval(
            "SELECT AVG(composite_score) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1",
            site_id,
        )

        # Update prospect
        await db.execute(
            "UPDATE prospects SET status = 'audited', audit_score = $1 WHERE id = $2",
            round(avg_health or 0), prospect_id,
        )

        # If we have an email, generate PDF and schedule drip
        if email:
            from app.routers.audit_report import _build_audit_data_for_site
            from app.services.drip_sequence import DripSequenceService
            from app.services.pdf_report import generate_audit_pdf

            site = await db.fetchrow("SELECT * FROM sites WHERE id = $1", site_id)
            audit_data = await _build_audit_data_for_site(db, site_id, dict(site))
            pdf_bytes = generate_audit_pdf(audit_data)

            drip = DripSequenceService()
            await drip.schedule_drip(db, email, domain, site_id, audit_data, pdf_bytes)

            await db.execute(
                "UPDATE prospects SET status = 'contacted', contacted_at = NOW() WHERE id = $1",
                prospect_id,
            )
            logger.info("Prospect %s audited and contacted at %s", domain, email)
        else:
            logger.info("Prospect %s audited but no email found", domain)

        return {
            "prospect_id": str(prospect_id),
            "domain": domain,
            "status": "contacted" if email else "audited",
            "audit_score": round(avg_health or 0),
            "email": email,
        }

    except Exception as e:
        logger.error("Prospect audit failed for %s: %s", domain, e)
        await db.execute(
            "UPDATE prospects SET status = 'discovered', notes = $1 WHERE id = $2",
            f"Audit failed: {str(e)[:200]}", prospect_id,
        )
        return {"error": str(e)[:200]}


async def enrich_prospect_emails(db: asyncpg.Connection, limit: int = 50) -> int:
    """Find contact emails for prospects that don't have one.

    Called as a background job to enrich prospect records.
    """
    rows = await db.fetch(
        """SELECT id, domain FROM prospects
           WHERE contact_email IS NULL AND status IN ('discovered', 'audited')
           ORDER BY created_at DESC LIMIT $1""",
        limit,
    )

    enriched = 0
    for row in rows:
        email = await find_contact_email(row["domain"])
        if email:
            await db.execute(
                "UPDATE prospects SET contact_email = $1 WHERE id = $2",
                email, row["id"],
            )
            enriched += 1
            logger.info("Found email %s for prospect %s", email, row["domain"])

    logger.info("Enriched %d/%d prospects with emails", enriched, len(rows))
    return enriched
