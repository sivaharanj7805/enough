"""Shareable audit report endpoint.

Returns a structured JSON report for a site that can be rendered
as a public shareable page or exported to PDF.

Includes a public PDF audit endpoint (no auth) that accepts URL + email,
enforces a 50-post limit and rate limits (3 per email per day).
"""

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
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

BANNED_PHRASES = [
    "comprehensive guide", "in-depth analysis", "expert recommendations",
    "actionable tips", "best practices", "everything you need to know",
    "key strategies", "practical examples", "learn everything about",
    "covering key", "this resource covers", "expert insights",
    "improvement opportunities", "optimization potential", "areas for enhancement",
    "visibility enhancements", "search visibility enhancements",
    "requires immediate implementation", "critical gap requiring",
]


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
    word_count: int = 0
    meta_description: str = ""
    suggested_meta: str = ""


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


@router.get("/{site_id}/audit-report/pdf")
async def download_audit_pdf(
    site_id: UUID,
    user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[asyncpg.Connection, Depends(get_db)],
):
    """Download PDF audit report for authenticated user's site."""
    site = await db.fetchrow(
        "SELECT id, name, domain, last_crawl_at FROM sites WHERE id = $1 AND user_id = $2",
        site_id, user_id,
    )
    if not site:
        raise HTTPException(404, "Site not found")

    data = await _build_audit_data_for_site(db, site_id, dict(site))

    from app.services.pdf_report import generate_audit_pdf
    pdf_bytes = generate_audit_pdf(data)

    domain = site["domain"] or "site"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="tended-audit-{domain}.pdf"',
        },
    )


# ──────────────── Public PDF Audit Endpoint (no auth) ────────────────


def _extract_numbers(text: str) -> list[int]:
    """Extract all numbers from text."""
    return [int(n) for n in re.findall(r'\b(\d+)\b', text)]


async def _generate_specific_meta(
    title: str, url: str, word_count: int,
    crawled_meta: str = "", rec_summaries: list[str] | None = None,
    body_text: str = "",
) -> str:
    """Use Claude + intelligence pipeline data to generate a specific meta description.

    Feeds the crawled meta, recommendation summaries, and body_text so Claude
    writes from actual page data, not just the title. Returns empty string on
    failure. Retries up to 3 times if the output contains a banned phrase.
    """
    from app.config import get_settings
    _settings = get_settings()
    if not _settings.anthropic_api_key or not title:
        return ""

    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=_settings.anthropic_api_key)

        # Build context from pipeline data
        context_parts = []
        if crawled_meta:
            context_parts.append(f"Current meta description (from the live page): {crawled_meta}")
        if body_text:
            context_parts.append(f"Post body text (first 2000 chars):\n{body_text[:2000]}")
        if rec_summaries:
            context_parts.append("Intelligence pipeline findings:\n" + "\n".join(
                f"- {s[:200]}" for s in rec_summaries[:3]
            ))

        context_block = "\n\n".join(context_parts) if context_parts else ""

        base_prompt = f"""Write a better meta description for this blog post.

Post title: {title}
Post URL: {url}
Word count: {word_count:,}

{context_block}

STRICT RULES:
- Exactly 140-155 characters (hard limit)
- Use SPECIFIC details from the current meta description and page data above
- Reference actual numbers, template names, categories, or tools mentioned IN THE BODY TEXT
- NEVER invent numbers, percentages, or statistics not present in the body text above. If the body says "23 templates", say 23. Do NOT say "50+" or "800%" unless that exact number appears in the text
- If you are given a 'current meta description', do NOT use any number larger than what appears in the current meta. Match or reduce the numbers, never inflate them
- NEVER use filler: "comprehensive guide", "expert insights", "actionable tips", "everything you need", "best practices", "key strategies", "in-depth analysis"
- NEVER start with "This" or "Learn" or "Discover" or "Access"
- Start with a number or verb
- Write as if you read the actual page and are describing exactly what someone will find
- Every factual claim must be verifiable from the body text provided

Return ONLY the meta description text. No quotes, no explanation."""

        prompt = base_prompt
        max_retries = 3

        for attempt in range(max_retries + 1):
            response = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )
            meta = response.content[0].text.strip().strip('"').strip("'")

            # Check for banned phrases
            meta_lower = meta.lower()
            found_banned = None
            for phrase in BANNED_PHRASES:
                if phrase in meta_lower:
                    found_banned = phrase
                    break

            if found_banned is None:
                # Number consistency check — prevent inflated numbers
                if crawled_meta:
                    current_nums = _extract_numbers(crawled_meta)
                    suggested_nums = _extract_numbers(meta)
                    if current_nums and suggested_nums:
                        max_current = max(current_nums)
                        needs_regen = any(sn > max_current * 1.5 for sn in suggested_nums)
                        if needs_regen:
                            logger.warning(
                                "Claude meta number inflation detected: current max=%d, suggested nums=%s — regenerating",
                                max_current, suggested_nums,
                            )
                            retry_prompt = (
                                f"{base_prompt}\n\nIMPORTANT: The current meta says: '{crawled_meta}'. "
                                f"Do NOT use any number larger than what appears in the current meta. "
                                f"If it says 23, say 23, not 50+."
                            )
                            response = await client.messages.create(
                                model="claude-haiku-4-5-20251001",
                                max_tokens=100,
                                messages=[{"role": "user", "content": retry_prompt}],
                            )
                            meta = response.content[0].text.strip().strip('"').strip("'")

                # No banned phrase — return result
                if 50 <= len(meta) <= 170:
                    return meta
                return meta[:160]

            # Banned phrase found — retry with extra instruction
            if attempt < max_retries:
                prompt = base_prompt + f"\n\nYour previous response contained '{found_banned}'. Do NOT use that phrase. Try again."
                logger.warning(
                    "Claude meta retry %d/%d: banned phrase '%s' found",
                    attempt + 1, max_retries, found_banned,
                )
            else:
                # All retries exhausted — return empty string for fallback
                logger.warning(
                    "Claude meta generation exhausted %d retries due to banned phrases, returning empty",
                    max_retries,
                )
                return ""

        return ""
    except Exception as e:
        logger.warning("Claude meta description generation failed: %s", e)
        return ""


def _validate_claude_output(text: str, input_numbers: set[str] | None = None) -> bool:
    """Validate Claude output against banned phrases and optional number consistency.

    Returns True if valid, False if any check fails.
    """
    text_lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in text_lower:
            logger.warning("Claude output validation failed: banned phrase '%s'", phrase)
            return False
    # If input numbers provided, verify all numbers in output exist in input
    if input_numbers is not None:
        output_numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', text))
        for num in output_numbers:
            # Strip % for comparison
            num_clean = num.rstrip('%')
            if num_clean not in input_numbers and num not in input_numbers:
                # Allow numbers <= 100 (common in percentages, scores, thresholds)
                # Only flag numbers > 100 that aren't in the input (e.g., "800% growth")
                try:
                    n = float(num_clean)
                    if n <= 100:
                        continue
                except ValueError:
                    pass
                logger.warning(
                    "Claude output validation failed: number '%s' not in input data %s",
                    num, input_numbers,
                )
                return False
    return True


def _build_input_numbers(*values: int | float | str | None) -> set[str]:
    """Build a set of string representations of input numbers for validation."""
    nums: set[str] = set()
    for v in values:
        if v is None:
            continue
        if isinstance(v, float):
            nums.add(str(int(v)) if v == int(v) else str(round(v, 1)))
            nums.add(str(int(round(v))))
            nums.add(f"{v:.0f}")
            nums.add(f"{v:.1f}")
        elif isinstance(v, int):
            nums.add(str(v))
        else:
            nums.add(str(v))
    return nums


async def _generate_executive_summary(
    domain: str, score: int, total_posts: int, cluster_count: int,
    problem_count: int, rec_count: int, cann_pairs: int, cann_posts: int,
    orphan_count: int, thin_count: int,
    ai_cite: float, ai_schema: float,
    top_cluster: str, worst_cluster: str,
) -> str:
    """Generate a Claude-powered executive summary for the audit report.

    Returns empty string on failure so fallback templates work.
    """
    from app.config import get_settings
    _settings = get_settings()
    if not _settings.anthropic_api_key:
        return ""

    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=_settings.anthropic_api_key)

        prompt = f"""Write an executive summary for a content audit of {domain}.

EXACT DATA (use ONLY these numbers):
- Overall health score: {score}/100
- Total posts analyzed: {total_posts}
- Topic clusters: {cluster_count}
- Content issues found: {problem_count}
- Recommendations generated: {rec_count}
- Cannibalization pairs: {cann_pairs} (affecting {cann_posts} posts)
- Orphan posts (no internal links): {orphan_count}
- Thin content posts: {thin_count}
- AI citability score: {ai_cite}/100
- Structured data coverage: {ai_schema}/100

STRICT RULES:
- Exactly 2 short paragraphs. Paragraph 1: 2 sentences max. Paragraph 2: 2 sentences max
- TOTAL output must be under 400 characters
- Bold key numbers using **markers** (e.g., **{score}/100**, **{rec_count}**)
- Paragraph 1: "{domain}" scored {score}/100, what that means, {rec_count} recommendations generated
- Paragraph 2: {problem_count} content issues found, top 2 specific findings with consequences
- The domain name MUST be written exactly as "{domain}" — never capitalize it, never convert to a brand name, never say "Backlinko" when the domain is "backlinko.com"
- The {problem_count} issue count MUST appear in the paragraph text, not just implied
- State findings as facts, not euphemisms: "showing moderate issues" is OK. "significant improvement opportunities" is BANNED. "areas for enhancement" is BANNED. This is a diagnostic, not a sales pitch
- No pushy language: "requires immediate implementation" and "critical gap requiring action" are BANNED in the summary. State facts only
- Every number MUST come from the data above — do NOT invent or round
- NEVER use: "comprehensive", "in-depth", "actionable", "best practices", "improvement opportunities", "optimization potential", "areas for enhancement"
- NEVER reference data types not in the data above: no "keyword rankings", no "traffic", no "keyword authority"

Return ONLY the 2 paragraphs separated by a blank line."""

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = response.content[0].text.strip()

        # Validate output
        input_nums = _build_input_numbers(
            score, total_posts, cluster_count, problem_count, rec_count,
            cann_pairs, cann_posts, orphan_count, thin_count, ai_cite, ai_schema,
        )
        # Add commonly derived percentages
        input_nums.update({"100", "0"})
        if not _validate_claude_output(summary, input_nums):
            return ""

        # Check line limit (max 6 lines across 2 paragraphs)
        lines = [ln for ln in summary.split('\n') if ln.strip()]
        if len(lines) > 8:  # generous limit accounting for paragraph break
            logger.warning("Claude executive summary exceeded line limit (%d lines)", len(lines))
            return ""

        return summary

    except Exception as e:
        logger.warning("Claude executive summary generation failed: %s", e)
        return ""


async def _generate_quick_win(
    win_type: str, title: str, context: str,
) -> dict:
    """Generate a Claude-powered quick win description.

    Returns {"description": "...", "impact": "..."} or empty dict on failure.
    """
    from app.config import get_settings
    _settings = get_settings()
    if not _settings.anthropic_api_key or not title:
        return {}

    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=_settings.anthropic_api_key)

        prompt = f"""Write a quick win description for a content audit recommendation.

Win type: {win_type}
Win title: {title}

Context data:
{context}

STRICT RULES:
- "description": exactly 1 sentence, max 20 words. Explain WHY this matters — do NOT restate the title
- "impact": exactly 1 short phrase with a SPECIFIC NUMBER from the context, max 12 words
- Impact MUST include a number from the context (e.g., "for 100% of your 149 posts" not "across your entire blog")
- No jargon, no filler. Be specific to the data provided
- NEVER reference data types not in the context: no "keyword authority", no "keyword rankings", no "traffic increase", no "keyword consolidation". Only reference data types that appear in the context above
- NEVER use: "comprehensive", "in-depth", "actionable", "best practices", "will increase", "will boost", "enhancements", "visibility enhancements"
- Use "enables", "qualifies for", "reduces" — not "will" promises

Return EXACTLY in this format (no other text):
DESCRIPTION: <your description>
IMPACT: <your impact line>"""

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Parse the structured output
        description = ""
        impact = ""
        for line in raw.split('\n'):
            line = line.strip()
            if line.upper().startswith("DESCRIPTION:"):
                description = line[len("DESCRIPTION:"):].strip()
            elif line.upper().startswith("IMPACT:"):
                impact = line[len("IMPACT:"):].strip()

        if not description or not impact:
            logger.warning("Claude quick win parsing failed for '%s': raw=%s", title, raw[:200])
            return {}

        # Validate
        if not _validate_claude_output(description) or not _validate_claude_output(impact):
            return {}

        return {"title": title, "win_type": win_type, "description": description, "impact": impact}

    except Exception as e:
        logger.warning("Claude quick win generation failed for '%s': %s", title, e)
        return {}


async def _generate_quick_wins_batch(
    top_clusters: list[dict],
    top_cann_pairs: list[dict],
    top_recs: list[dict],
    ai_schema: float | None,
    cann_pairs: int,
    total_posts: int,
) -> list[dict]:
    """Determine and generate 3 quick wins in parallel.

    Selection logic:
    1. If ai_schema == 0: "Add structured data to your top posts"
    2. If cann pairs exist: top cann pair consolidation
    3. From top_recs: FAQ or other recommendation

    Returns list of dicts with title/description/impact, or empty list on failure.
    """
    wins_to_generate: list[tuple[str, str, str]] = []  # (win_type, title, context)

    # Win 1: Schema data if score is 0
    if ai_schema is not None and ai_schema == 0:
        context = (
            f"Schema coverage: {ai_schema}% across {total_posts} posts. "
            f"No posts have structured data (Article, FAQ, HowTo markup)."
        )
        wins_to_generate.append((
            "schema",
            "Add structured data to your top posts",
            context,
        ))
    elif top_recs:
        # Use highest-priority rec as first win
        rec = top_recs[0]
        context = (
            f"Recommendation: {rec.get('title', '')}. "
            f"Summary: {rec.get('summary', 'N/A')}. "
            f"Affected post: {rec.get('post_title', '')} ({rec.get('post_url', '')})."
        )
        wins_to_generate.append((
            rec.get("rec_type", "optimization"),
            rec.get("title", "Optimize top content"),
            context,
        ))

    # Win 2: Cannibalization consolidation
    if cann_pairs > 0 and top_cann_pairs:
        pair = top_cann_pairs[0]
        context = (
            f"Top cannibalization pair: \"{pair.get('post_a_title', '')}\" vs \"{pair.get('post_b_title', '')}\". "
            f"Overlap score: {pair.get('overlap_score', 0)}. Severity: {pair.get('severity', 'medium')}. "
            f"Total cannibalization pairs: {cann_pairs}."
        )
        wins_to_generate.append((
            "cannibalization",
            f"Consolidate \"{pair.get('post_a_title', '')[:40]}\" and \"{pair.get('post_b_title', '')[:40]}\"",
            context,
        ))
    elif len(top_recs) > 1:
        rec = top_recs[1]
        context = (
            f"Recommendation: {rec.get('title', '')}. "
            f"Summary: {rec.get('summary', 'N/A')}. "
            f"Affected post: {rec.get('post_title', '')}."
        )
        wins_to_generate.append((
            rec.get("rec_type", "optimization"),
            rec.get("title", "Improve content quality"),
            context,
        ))

    # Win 3: Pick a DIFFERENT type than Wins 1-2 (not schema/structured data/FAQ)
    used_types = {w[0] for w in wins_to_generate}
    schema_types = {"schema", "add_schema", "faq", "add_faq_section", "add_faq"}
    used_titles = {w[1] for w in wins_to_generate}
    # Find a rec that's a genuinely different type (interlink, expand, refresh, etc.)
    diff_rec = next(
        (r for r in top_recs
         if (r.get("rec_type") or "").lower() not in schema_types
         and "schema" not in (r.get("title") or "").lower()
         and "structured data" not in (r.get("title") or "").lower()
         and "faq" not in (r.get("title") or "").lower()
         and r.get("title") not in used_titles),
        None,
    )
    if diff_rec:
        rec = diff_rec
        context = (
            f"Recommendation: {rec.get('title', '')}. "
            f"Summary: {rec.get('summary', 'N/A')}. "
            f"Affected post: {rec.get('post_title', '')}."
        )
        wins_to_generate.append((
            rec.get("rec_type", "optimization"),
            rec.get("title", "Fix content quality issues"),
            context,
        ))
    else:
        # Fall back to next available rec
        remaining = [r for r in top_recs if r.get("title") not in used_titles]
        if remaining:
            rec = remaining[0]
            context = (
                f"Recommendation: {rec.get('title', '')}. "
                f"Summary: {rec.get('summary', 'N/A')}. "
                f"Affected post: {rec.get('post_title', '')}."
            )
            wins_to_generate.append((
                rec.get("rec_type", "optimization"),
                rec.get("title", "Optimize content structure"),
                context,
            ))

    if not wins_to_generate:
        return []

    # Cap at 3 wins
    wins_to_generate = wins_to_generate[:3]

    # Generate all wins in parallel
    results = await asyncio.gather(
        *[_generate_quick_win(wt, title, ctx) for wt, title, ctx in wins_to_generate],
        return_exceptions=True,
    )

    wins = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Quick win generation %d failed: %s", i, result)
            continue
        if result:  # non-empty dict
            wins.append(result)

    return wins


async def _generate_what_this_means(
    cite: float, eeat: float, schema: float, extraction: float,
    pct_ready: float, pct_schema: float, pct_faq: float, total_posts: int,
) -> str:
    """Generate a Claude-powered 'What this means' box for AI readiness section.

    Returns empty string on failure so fallback templates work.
    """
    from app.config import get_settings
    _settings = get_settings()
    if not _settings.anthropic_api_key:
        return ""

    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=_settings.anthropic_api_key)

        # Determine weakest dimension
        dimensions = {
            "AI Citability": cite,
            "E-E-A-T signals": eeat,
            "Schema markup": schema,
            "Content extraction": extraction,
        }
        weakest_name = min(dimensions, key=dimensions.get)
        weakest_score = dimensions[weakest_name]

        # Use integer versions — these are what actually appear in the rendered report
        i_cite = int(cite)
        i_eeat = int(eeat)
        i_schema = int(schema)
        i_extract = int(extraction)
        i_pct_ready = int(pct_ready)
        i_pct_schema = int(pct_schema)
        i_pct_faq = int(pct_faq)
        i_weakest = int(weakest_score)

        prompt = f"""Write a "What this means" explanation for a content audit's AI readiness section.

EXACT DATA (use ONLY these integer values — no decimals, no derived calculations):
- AI Citability score: {i_cite}/100
- E-E-A-T score: {i_eeat}/100
- Structured data coverage: {i_schema}/100
- Content extraction score: {i_extract}/100
- Posts with structured data: {i_pct_schema}%
- Posts with FAQ sections: {i_pct_faq}%
- Total posts: {total_posts}
- WEAKEST dimension: {weakest_name} at {i_weakest}/100

STRICT RULES:
- Exactly 2-3 sentences
- Sentence 1: State the problem in plain language, focused on the weakest dimension ({weakest_name})
- Sentence 2: State the single most important action to take
- Sentence 3 (OPTIONAL): A brief supporting statement using ONLY numbers from the EXACT DATA block above. Do NOT introduce any external statistics (no "34.5%", no "50%", no CTR stats)
- Do NOT introduce ANY number that isn't EXACTLY listed in the EXACT DATA block above. The ONLY numbers you may use are: {cite}, {eeat}, {schema}, {extraction}, {pct_ready}, {pct_schema}, {pct_faq}, {total_posts}. ANY other number is a FAIL — no derived calculations, no external stats
- Use the same terminology as the rest of the report: "structured data" not "schema markup"
- NEVER invent statistics or cite unverifiable claims
- NEVER use: "comprehensive", "in-depth", "actionable", "best practices"
- NEVER reference data types not in the data: no "keyword rankings", no "traffic"

Return ONLY the 2-3 sentences. No heading, no quotes, no bullet points."""

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Build input numbers for validation (include the two allowed stat numbers)
        input_nums = _build_input_numbers(
            cite, eeat, schema, extraction, pct_ready, pct_schema, pct_faq,
            total_posts, weakest_score,
        )
        # Add the two allowed statistics' numbers
        input_nums.update({"50", "34.5", "34"})

        if not _validate_claude_output(text, input_nums):
            return ""

        # Check sentence count (2-3 sentences)
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        if len(sentences) > 4:  # generous limit
            logger.warning("Claude 'what this means' exceeded sentence limit (%d sentences)", len(sentences))
            return ""

        return text

    except Exception as e:
        logger.warning("Claude 'what this means' generation failed: %s", e)
        return ""


async def _build_audit_data_for_site(db: asyncpg.Connection, site_id: UUID, site: dict) -> dict:
    """Build audit report data dict for a site (reusable by PDF + JSON endpoints)."""
    total_posts = await db.fetchval("SELECT COUNT(*) FROM posts WHERE site_id = $1", site_id) or 0
    overall_health = await db.fetchval(
        "SELECT AVG(composite_score) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1",
        site_id,
    ) or 0
    # Count leaf clusters (clusters that have no children) — these are what's displayed
    cluster_count = await db.fetchval(
        """SELECT COUNT(*) FROM clusters WHERE site_id = $1
           AND id NOT IN (
               SELECT parent_cluster_id FROM clusters
               WHERE parent_cluster_id IS NOT NULL AND site_id = $1
           )
           AND post_count > 0""",
        site_id,
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

    # Meta description coverage (Gap 26)
    meta_desc_row = await db.fetchrow(
        """SELECT
            COUNT(*) FILTER (WHERE meta_description IS NOT NULL AND meta_description != '') * 100.0
                / NULLIF(COUNT(*), 0) AS pct,
            COUNT(*) FILTER (WHERE meta_description IS NULL OR meta_description = '') AS missing
        FROM posts WHERE site_id = $1""",
        site_id,
    )
    meta_desc_pct = round(float(meta_desc_row["pct"]), 1) if meta_desc_row and meta_desc_row["pct"] is not None else 0.0
    meta_missing_count = int(meta_desc_row["missing"] or 0) if meta_desc_row else 0

    # Count distinct posts involved in cannibalization (not pairs)
    cann_post_count = await db.fetchval(
        """SELECT COUNT(DISTINCT post_id) FROM (
            SELECT cp.post_a_id AS post_id FROM cannibalization_pairs cp
            JOIN clusters cl ON cl.id = cp.cluster_id WHERE cl.site_id = $1
            UNION
            SELECT cp.post_b_id AS post_id FROM cannibalization_pairs cp
            JOIN clusters cl ON cl.id = cp.cluster_id WHERE cl.site_id = $1
        ) sub""",
        site_id,
    ) or 0

    # Top clusters — show leaf clusters (no children) sorted by size
    cluster_rows = await db.fetch(
        """SELECT label, description, post_count, health_score, ecosystem_state
           FROM clusters WHERE site_id = $1
             AND id NOT IN (
                 SELECT parent_cluster_id FROM clusters
                 WHERE parent_cluster_id IS NOT NULL AND site_id = $1
             )
             AND post_count > 0
           ORDER BY post_count DESC LIMIT 8""",
        site_id,
    )
    top_clusters = [
        {"label": r["label"] or "Unnamed Cluster", "description": r["description"],
         "post_count": r["post_count"] or 0, "health_score": round(r["health_score"] or 0),
         "ecosystem_state": r["ecosystem_state"] or "seedbed"}
        for r in cluster_rows
    ]

    # Top cann pairs (DISTINCT ON avoids duplicates from recommendation JOIN)
    cann_rows = await db.fetch(
        """SELECT DISTINCT ON (cp.id)
                  pa.title AS a_title, pa.url AS a_url,
                  pb.title AS b_title, pb.url AS b_url,
                  cp.cosine_similarity, cp.severity
           FROM cannibalization_pairs cp
           JOIN clusters cl ON cl.id = cp.cluster_id
           JOIN posts pa ON pa.id = cp.post_a_id
           JOIN posts pb ON pb.id = cp.post_b_id
           WHERE cl.site_id = $1
           ORDER BY cp.id, cp.cosine_similarity DESC""",
        site_id,
    )
    # Re-sort by similarity after dedup and take top 8
    cann_sorted = sorted(cann_rows, key=lambda r: r["cosine_similarity"] or 0, reverse=True)[:8]
    top_cann_pairs = [
        {"post_a_title": r["a_title"] or "", "post_a_url": r["a_url"] or "",
         "post_b_title": r["b_title"] or "", "post_b_url": r["b_url"] or "",
         "overlap_score": round(r["cosine_similarity"] or 0, 3),
         "severity": r["severity"] or "medium", "recommendation": None}
        for r in cann_sorted
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

    # Worst posts — deduplicated by post, aggregated issues, ranked by severity weight sum
    worst_rows = await db.fetch(
        """SELECT DISTINCT ON (p.id)
                  p.title, p.url, p.word_count, p.meta_description,
                  phs.composite_score, phs.role,
                  (SELECT string_agg(DISTINCT cp2.problem_type, ', ')
                   FROM content_problems cp2 WHERE cp2.post_id = p.id) AS issues,
                  (SELECT COALESCE(SUM(COALESCE((cp3.details->>'severity_score')::int, 50)), 0)
                   FROM content_problems cp3 WHERE cp3.post_id = p.id) AS severity_weight_sum
           FROM posts p
           JOIN post_health_scores phs ON phs.post_id = p.id
           WHERE p.site_id = $1 AND p.word_count >= 200
           ORDER BY p.id, phs.composite_score ASC NULLS LAST""",
        site_id,
    )
    # Sort: posts with problems first, then by severity weight sum descending,
    # then by composite_score ascending as tiebreaker. This ensures a post with
    # 3 high-severity issues outranks one with 6 low-severity issues.
    worst_sorted = sorted(
        worst_rows,
        key=lambda r: (0 if r["issues"] else 1, -(r["severity_weight_sum"] or 0), r["composite_score"] or 999),
    )
    worst_posts = [
        {"title": r["title"] or "", "url": r["url"] or "",
         "word_count": r["word_count"] or 0,
         "meta_description": r["meta_description"] or "",
         "health_score": round(r["composite_score"] or 0),
         "role": r["role"] or "dead_weight", "issue": r["issues"] or "low health score"}
        for r in worst_sorted[:5]
    ]

    # Generate a Claude-powered meta description for the Example Fix post.
    # ALWAYS use worst_posts[0] — the #1 lowest-scoring post from the Top 5 table.
    # Showing a different post breaks trust (prospect sees #1 in the table above).
    # If #1 has a meta, show "current vs improved". If not, show "none vs suggested".
    ef_post_idx = 0
    ef_has_meta = False
    if worst_posts:
        ef_has_meta = bool((worst_posts[0].get("meta_description") or "").strip())

        ef_post = worst_posts[ef_post_idx]

        # Fetch recommendation summaries for the EF post from the pipeline
        ef_url = ef_post["url"]
        worst_recs = await db.fetch(
            """SELECT r.summary FROM recommendations r
               JOIN posts p ON p.id = r.post_id
               WHERE p.site_id = $1 AND p.url = $2
               ORDER BY CASE r.priority
                   WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                   WHEN 'medium' THEN 2 ELSE 3 END
               LIMIT 3""",
            site_id, ef_url,
        )
        rec_summaries = [r["summary"] for r in worst_recs] if worst_recs else []

        # Fetch body_text for the EF post (first 2000 chars)
        ef_body_text = await db.fetchval(
            "SELECT LEFT(body_text, 2000) FROM posts WHERE url = $1 AND site_id = $2 LIMIT 1",
            ef_url, site_id,
        ) or ""

        worst_post_meta_suggestion = await _generate_specific_meta(
            ef_post["title"], ef_post["url"],
            ef_post["word_count"],
            crawled_meta=ef_post.get("meta_description", ""),
            rec_summaries=rec_summaries,
            body_text=ef_body_text,
        )
        if worst_post_meta_suggestion:
            worst_posts[ef_post_idx]["suggested_meta"] = worst_post_meta_suggestion

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

    # GEO detail stats from ai_signals JSONB — used by PDF for "Why AI skips your content"
    geo_detail = await db.fetchrow(
        """
        SELECT
            ROUND(AVG((phs.ai_signals->>'data_density_per_200w')::float)::numeric, 1) AS avg_data_density,
            ROUND(AVG((phs.ai_signals->>'question_header_ratio')::float)::numeric, 2) AS avg_question_header_ratio,
            ROUND(COUNT(*) FILTER (WHERE (phs.ai_signals->>'extract_has_faq_section')::boolean = true)::numeric /
                  NULLIF(COUNT(*), 0) * 100, 1) AS pct_has_faq
        FROM post_health_scores phs
        JOIN posts p ON p.id = phs.post_id
        WHERE p.site_id = $1 AND phs.ai_signals IS NOT NULL
        """,
        site_id,
    )
    avg_data_density = float(geo_detail["avg_data_density"]) if geo_detail and geo_detail["avg_data_density"] is not None else None
    avg_question_ratio = float(geo_detail["avg_question_header_ratio"]) if geo_detail and geo_detail["avg_question_header_ratio"] is not None else None
    pct_has_faq = float(geo_detail["pct_has_faq"]) if geo_detail and geo_detail["pct_has_faq"] is not None else None

    # Key findings
    key_findings: list[str] = []
    if cann_pair_count > 0:
        key_findings.append(
            f"{cann_post_count} of your {total_posts} posts have significant content overlap "
            f"({cann_pair_count} cannibalization pairs detected)"
        )
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
            key_findings.append(f"{100 - ai_pct_schema:.0f}% of posts have no structured data (schema markup) — missing Article/FAQ markup that increases AI Overview citations")

    # Content Profile stats
    content_profile = await db.fetchrow(
        """
        SELECT
            ROUND(AVG(word_count)::numeric, 0) AS avg_wc,
            ROUND(AVG(readability_score)::numeric, 1) AS avg_read,
            COUNT(*) FILTER (WHERE modified_date > NOW() - INTERVAL '6 months') AS u6,
            COUNT(*) FILTER (WHERE modified_date > NOW() - INTERVAL '12 months') AS u12,
            COUNT(*) FILTER (WHERE modified_date > NOW() - INTERVAL '24 months') AS u24,
            COUNT(*) FILTER (WHERE modified_date <= NOW() - INTERVAL '24 months'
                             OR modified_date IS NULL) AS stale
        FROM posts WHERE site_id = $1 AND word_count > 50
        """,
        site_id,
    )
    # Internal linking stats
    link_stats = await db.fetchrow(
        """
        SELECT ROUND(AVG(cnt)::numeric, 1) AS avg_in, MAX(cnt) AS max_in
        FROM (
            SELECT target_post_id, COUNT(*) AS cnt
            FROM internal_links WHERE site_id = $1 AND target_post_id IS NOT NULL
            GROUP BY target_post_id
        ) sub
        """,
        site_id,
    )
    most_linked = await db.fetchrow(
        """
        SELECT p.title, COUNT(*) AS cnt
        FROM internal_links il JOIN posts p ON p.id = il.target_post_id
        WHERE il.site_id = $1 AND il.target_post_id IS NOT NULL
        GROUP BY p.title ORDER BY cnt DESC LIMIT 1
        """,
        site_id,
    )

    # Headline
    if cann_pair_count >= 50:
        headline = f"{cann_post_count} of {total_posts} posts have significant content overlap across {cluster_count} topic clusters"
    elif rec_count >= 100:
        headline = f"Generated {rec_count} specific recommendations across {total_posts} posts"
    else:
        headline = f"Analyzed {total_posts} posts across {cluster_count} topic clusters — {problem_count} issues detected"

    # ──────────────── Run Claude AI enhancements in parallel ────────────────
    # Determine top/worst cluster labels for executive summary
    _top_cluster_label = top_clusters[0]["label"] if top_clusters else "N/A"
    _worst_cluster_label = (
        min(top_clusters, key=lambda c: c["health_score"])["label"]
        if top_clusters else "N/A"
    )

    # Safe defaults for AI scores (use 0.0 if None for Claude calls)
    _ai_cite = ai_cite if ai_cite is not None else 0.0
    _ai_eeat = ai_eeat if ai_eeat is not None else 0.0
    _ai_schema = ai_schema if ai_schema is not None else 0.0
    _ai_extract = ai_extract if ai_extract is not None else 0.0
    _ai_pct_ready = ai_pct_ready if ai_pct_ready is not None else 0.0
    _ai_pct_schema = ai_pct_schema if ai_pct_schema is not None else 0.0
    _pct_has_faq = pct_has_faq if pct_has_faq is not None else 0.0

    ai_summary, ai_wtm, ai_wins = await asyncio.gather(
        _generate_executive_summary(
            domain=site.get("domain", ""),
            score=round(overall_health),
            total_posts=int(total_posts),
            cluster_count=int(cluster_count),
            problem_count=int(problem_count),
            rec_count=int(rec_count),
            cann_pairs=int(cann_pair_count),
            cann_posts=int(cann_post_count),
            orphan_count=int(orphan_count),
            thin_count=int(thin_count),
            ai_cite=_ai_cite,
            ai_schema=_ai_schema,
            top_cluster=_top_cluster_label,
            worst_cluster=_worst_cluster_label,
        ),
        _generate_what_this_means(
            cite=_ai_cite,
            eeat=_ai_eeat,
            schema=_ai_schema,
            extraction=_ai_extract,
            pct_ready=_ai_pct_ready,
            pct_schema=_ai_pct_schema,
            pct_faq=_pct_has_faq,
            total_posts=int(total_posts),
        ),
        _generate_quick_wins_batch(
            top_clusters=top_clusters,
            top_cann_pairs=top_cann_pairs,
            top_recs=top_recs,
            ai_schema=ai_schema,
            cann_pairs=int(cann_pair_count),
            total_posts=int(total_posts),
        ),
        return_exceptions=True,
    )
    # Handle exceptions gracefully — fall back to empty values
    if isinstance(ai_summary, Exception):
        logger.warning("AI executive summary failed: %s", ai_summary)
        ai_summary = ""
    if isinstance(ai_wtm, Exception):
        logger.warning("AI 'what this means' failed: %s", ai_wtm)
        ai_wtm = ""
    if isinstance(ai_wins, Exception):
        logger.warning("AI quick wins failed: %s", ai_wins)
        ai_wins = []

    return {
        "site_name": site.get("name") or site.get("domain", ""),
        "site_domain": site.get("domain", ""),
        "total_posts": int(total_posts),
        "analyzed_at": site["last_crawl_at"].isoformat() if site.get("last_crawl_at") else None,
        "overall_health": round(overall_health),
        "cluster_count": int(cluster_count),
        "problem_count": int(problem_count),
        "rec_count": int(rec_count),
        "cann_pair_count": int(cann_pair_count),
        "cann_post_count": int(cann_post_count),
        "orphan_count": int(orphan_count),
        "thin_content_count": int(thin_count),
        "exact_duplicate_count": int(exact_dup_count),
        "meta_desc_pct": meta_desc_pct,
        "meta_missing_count": meta_missing_count,
        "ef_post_idx": ef_post_idx,
        "ef_has_meta": ef_has_meta,
        "ai_citability_score": ai_cite,
        "ai_eeat_score": ai_eeat,
        "ai_schema_score": ai_schema,
        "ai_extraction_score": ai_extract,
        "ai_pct_ready": ai_pct_ready,
        "ai_pct_schema": ai_pct_schema,
        "avg_data_density": avg_data_density,
        "avg_question_header_ratio": avg_question_ratio,
        "pct_has_faq": pct_has_faq,
        "score_confidence": "crawl_only",  # TODO: detect from GA4/GSC presence
        "top_clusters": top_clusters,
        "top_cann_pairs": top_cann_pairs,
        "top_recs": top_recs,
        "worst_posts": worst_posts,
        "best_posts": best_posts,
        "key_findings": key_findings,
        "headline": headline,
        # Content profile
        "avg_word_count": int(content_profile["avg_wc"] or 0) if content_profile else 0,
        "avg_readability": float(content_profile["avg_read"] or 0) if content_profile else 0,
        "updated_6mo": int(content_profile["u6"] or 0) if content_profile else 0,
        "updated_12mo": int(content_profile["u12"] or 0) if content_profile else 0,
        "updated_24mo": int(content_profile["u24"] or 0) if content_profile else 0,
        "stale_24mo": int(content_profile["stale"] or 0) if content_profile else 0,
        # Internal linking
        "avg_inbound_links": float(link_stats["avg_in"] or 0) if link_stats else 0,
        "most_linked_post": most_linked["title"] if most_linked else None,
        "most_linked_count": int(most_linked["cnt"]) if most_linked else 0,
        # Claude AI-generated report elements
        "ai_executive_summary": ai_summary,
        "ai_what_this_means": ai_wtm,
        "ai_quick_wins": ai_wins,
    }


@router.post("/audit-report/pdf")
@limiter.limit("6/minute")  # slowapi requires request: Request as first param
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
    today = datetime.now(UTC).date()
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
        "SELECT id, name, domain, last_crawl_at FROM sites WHERE lower(domain) = lower($1) LIMIT 1",
        domain,
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
            body.email, domain, site_id, datetime.now(UTC),
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
        body.email, domain, site_id, datetime.now(UTC),
    )

    # Build audit data and generate PDF
    audit_data = await _build_audit_data_for_site(db, site_id, dict(site))

    from app.services.pdf_report import generate_audit_pdf, verify_pdf_against_spec
    pdf_bytes = generate_audit_pdf(audit_data)

    # AI verification against spec (runs in background, logs failures)
    background_tasks.add_task(verify_pdf_against_spec, pdf_bytes, audit_data)

    # Schedule drip email sequence in background
    background_tasks.add_task(
        _schedule_drip_sequence, body.email, domain, site_id, audit_data, pdf_bytes,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="tended-audit-{domain}.pdf"',
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
            logger.exception("Failed to update pipeline status for site %s", site_id)


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

    admin_secret = settings.admin_secret
    if not admin_secret:
        raise HTTPException(503, "Admin endpoint not configured — set ADMIN_SECRET")

    provided = request.headers.get("X-Admin-Secret", "")
    if not provided:
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
        "SELECT id, name, domain, last_crawl_at FROM sites WHERE lower(domain) = lower($1) LIMIT 1",
        domain,
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
