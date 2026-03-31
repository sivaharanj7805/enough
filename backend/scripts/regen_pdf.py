"""Regenerate audit PDF from existing DB data (no re-crawl).

Includes self-correcting loop: generate → verify → fix → regenerate
until all 8 spec rule categories pass (max 3 iterations).
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/enough')

# ── Promise language patterns to strip ──
_PROMISE_PATTERNS = [
    (r"\bwill directly support\b", "supports"),
    (r"\bwill significantly\b", "can significantly"),
    (r"\bwill increase\b", "can increase"),
    (r"\bwill boost\b", "enables"),
    (r"\bwill improve\b", "can improve"),
    (r"\bwill drive\b", "enables"),
    (r"\bwill enable\b", "enables"),
    (r"\brequires immediate implementation\b", "is a high-priority fix"),
    (r"\bmust be addressed urgently\b", "should be addressed"),
    (r"\bcritical gap requiring\b", "notable gap in"),
    (r"\bimplement structured data markup\b", "add structured data"),
]

# ── Terminology fixes ──
_TERM_FIXES = [
    ("schema markup", "structured data"),
    ("Schema markup", "Structured data"),
    ("SCHEMA MARKUP", "STRUCTURED DATA"),
]


def _auto_fix_report_data(audit_data: dict, failures: list[dict]) -> dict:
    """Apply automated fixes to the report data based on verification failures.

    Modifies Claude-generated text fields to resolve common issues:
    - Promise language → capability language
    - Terminology inconsistencies → "structured data"
    - Missing Quick Win #3 fallback
    """
    changed = False

    # Fix all AI-generated text fields
    ai_fields = ["ai_executive_summary", "ai_what_this_means"]
    for key in ai_fields:
        text = audit_data.get(key, "")
        if not text:
            continue
        original = text
        # Fix promise language
        for pattern, replacement in _PROMISE_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        # Fix terminology
        for old, new in _TERM_FIXES:
            text = text.replace(old, new)
        if text != original:
            audit_data[key] = text
            changed = True

    # Fix Quick Win AI outputs
    ai_wins = audit_data.get("ai_quick_wins") or []
    for win in ai_wins:
        if not isinstance(win, dict):
            continue
        for field in ("description", "impact"):
            text = win.get(field, "")
            if not text:
                continue
            original = text
            for pattern, replacement in _PROMISE_PATTERNS:
                text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
            for old, new in _TERM_FIXES:
                text = text.replace(old, new)
            if text != original:
                win[field] = text
                changed = True

    # Fix key findings terminology
    kf = audit_data.get("key_findings") or []
    new_kf = []
    for finding in kf:
        original = finding
        for old, new in _TERM_FIXES:
            finding = finding.replace(old, new)
        new_kf.append(finding)
        if finding != original:
            changed = True
    if changed:
        audit_data["key_findings"] = new_kf

    return audit_data


def _print_verification(verification: dict) -> int:
    """Print verification results and return failure count."""
    fail_count = 0
    if verification.get("raw"):
        for line in verification["raw"].split("\n"):
            line = line.strip()
            if not line:
                continue
            # Only count numbered rule lines (1-8)
            is_rule_line = bool(re.match(r"^\d\.", line) or re.match(r"^\*?\*?\d\.", line))
            if "FAIL" in line.upper() and is_rule_line:
                print(f"  \u274c {line[:120]}")
                fail_count += 1
            elif "PASS" in line.upper() and "FAIL" not in line.upper() and is_rule_line:
                print(f"  \u2705 {line[:120]}")
            elif line.startswith("-") and "Offending" in line:
                print(f"     {line[:120]}")
    return fail_count


async def regen(domain: str):
    conn = await asyncpg.connect(DB_URL)

    site = await conn.fetchrow(
        "SELECT * FROM sites WHERE lower(domain) = lower($1)", domain
    )
    if not site:
        print(f"Site not found: {domain}")
        await conn.close()
        return

    site_id = site['id']
    site_dict = dict(site)
    print(f"Site: {site_id} ({domain})")

    # Use the same audit data builder as the API
    from app.routers.audit_report import _build_audit_data_for_site
    audit_data = await _build_audit_data_for_site(conn, site_id, site_dict)

    # Print summary
    print(f"  Health:          {audit_data['overall_health']}/100")
    print(f"  Posts:           {audit_data['total_posts']}")
    print(f"  Clusters:        {audit_data['cluster_count']}")
    print(f"  Problems:        {audit_data['problem_count']}")
    print(f"  Cann pairs:      {audit_data['cann_pair_count']}")
    print(f"  Cann posts:      {audit_data.get('cann_post_count', 'N/A')}")
    print(f"  Recommendations: {audit_data['rec_count']}")
    print(f"  Analyzed at:     {audit_data['analyzed_at']}")
    print(f"  AI Citability:   {audit_data.get('ai_citability_score')}")
    print(f"  AI Schema:       {audit_data.get('ai_schema_score')}")
    print(f"  Headline:        {audit_data['headline']}")
    print(f"  Key findings:")
    for f in audit_data['key_findings']:
        print(f"    - {f}")
    print(f"  Worst posts:")
    for p in audit_data['worst_posts']:
        print(f"    {p['health_score']}/100 [{p.get('issue', '---')}] {p['title'][:50]}")

    from app.services.pdf_report import generate_audit_pdf, verify_pdf_against_spec

    pdf_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        f"{domain.replace('.', '-')}-audit-report.pdf"
    )

    max_iterations = 3
    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"  ITERATION {iteration}/{max_iterations}")
        print(f"{'='*60}")

        # Generate PDF
        pdf_bytes = generate_audit_pdf(audit_data)
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)
        print(f"\n  PDF: {len(pdf_bytes) // 1024}KB -> {pdf_path}")

        # AI Verification
        print(f"\n  === AI SPEC VERIFICATION (iteration {iteration}) ===")
        verification = await verify_pdf_against_spec(pdf_bytes, audit_data)
        fail_count = _print_verification(verification)

        if fail_count == 0 or verification.get("pass"):
            print(f"\n  \u2705 ALL 8 RULES PASS — PDF is ready to send")
            break

        print(f"\n  {fail_count} failures found. ", end="")

        if iteration < max_iterations:
            print("Applying auto-fixes and regenerating...")
            # Auto-fix the report data based on failures
            audit_data = _auto_fix_report_data(audit_data, verification.get("failures", []))
        else:
            print(f"Max iterations reached. {fail_count} rules still failing.")
            print("  Manual review needed for remaining failures.")

    await conn.close()


if __name__ == "__main__":
    domain = sys.argv[1] if len(sys.argv) > 1 else "cookieandkate.com"
    asyncio.run(regen(domain))
