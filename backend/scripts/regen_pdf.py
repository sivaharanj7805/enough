"""Regenerate audit PDF from existing DB data (no re-crawl)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/enough')


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

    # Generate PDF
    from app.services.pdf_report import generate_audit_pdf
    pdf_bytes = generate_audit_pdf(audit_data)

    pdf_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        f"{domain.replace('.', '-')}-audit-report.pdf"
    )
    with open(pdf_path, 'wb') as f:
        f.write(pdf_bytes)

    print(f"\nPDF: {len(pdf_bytes) // 1024}KB -> {pdf_path}")
    await conn.close()


if __name__ == "__main__":
    domain = sys.argv[1] if len(sys.argv) > 1 else "cookieandkate.com"
    asyncio.run(regen(domain))
