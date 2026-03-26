"""Dump all analysis data for a site to stdout."""
import asyncio
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncpg

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/enough')


async def dump(site_id_str: str):
    conn = await asyncpg.connect(DB_URL)
    SITE_ID = uuid.UUID(site_id_str)
    out = []

    # 1. Site info
    site = await conn.fetchrow('SELECT * FROM sites WHERE id = $1', SITE_ID)
    if not site:
        print(f"Site {SITE_ID} not found")
        return
    out.append('# SITE INFO')
    out.append(f'id: {site["id"]}')
    out.append(f'domain: {site["domain"]}')
    out.append(f'cms_type: {site["cms_type"]}')
    out.append(f'created_at: {site["created_at"]}')
    out.append(f'last_crawl_at: {site.get("last_crawl_at")}')

    # 2. Post stats
    post_count = await conn.fetchval('SELECT count(*) FROM posts WHERE site_id = $1', SITE_ID)
    avg_wc = await conn.fetchval('SELECT avg(word_count) FROM posts WHERE site_id = $1', SITE_ID) or 0
    min_wc = await conn.fetchval('SELECT min(word_count) FROM posts WHERE site_id = $1', SITE_ID) or 0
    max_wc = await conn.fetchval('SELECT max(word_count) FROM posts WHERE site_id = $1', SITE_ID) or 0
    median_wc = await conn.fetchval(
        'SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY word_count) FROM posts WHERE site_id = $1', SITE_ID
    ) or 0
    out.append(f'\n# POST STATISTICS')
    out.append(f'total: {post_count}')
    out.append(f'word_count: avg={avg_wc:.0f}, median={median_wc:.0f}, min={min_wc}, max={max_wc}')

    # 3. All posts with scores
    rows = await conn.fetch('''
        SELECT p.id, p.title, p.url, p.word_count, p.content_intent,
               p.readability_score, p.grade_level, p.meta_description,
               phs.composite_score, phs.role, phs.trend,
               phs.freshness_score, phs.content_depth_score, phs.internal_link_score,
               phs.technical_seo_score,
               phs.internal_pagerank,
               phs.ai_citability_score, phs.eeat_score, phs.schema_score, phs.extraction_score
        FROM posts p
        LEFT JOIN post_health_scores phs ON p.id = phs.post_id
        WHERE p.site_id = $1
        ORDER BY phs.composite_score ASC NULLS LAST
    ''', SITE_ID)
    out.append(f'\n# ALL POSTS ({len(rows)} total, sorted by health score ascending)')
    out.append('')
    for i, r in enumerate(rows, 1):
        health = f"{r['composite_score']:.0f}" if r['composite_score'] is not None else "N/A"
        role = r['role'] or 'N/A'
        trend = r['trend'] or 'N/A'
        intent = r['content_intent'] or 'N/A'
        readability = f"{r['readability_score']:.1f}" if r['readability_score'] else 'N/A'
        grade = f"{r['grade_level']:.1f}" if r['grade_level'] else 'N/A'
        has_meta = 'yes' if r['meta_description'] else 'no'
        pagerank = f"{r['internal_pagerank']:.4f}" if r['internal_pagerank'] else 'N/A'

        ai_cite = f"{r['ai_citability_score']:.0f}" if r['ai_citability_score'] is not None else 'N/A'
        eeat = f"{r['eeat_score']:.0f}" if r['eeat_score'] is not None else 'N/A'
        schema = f"{r['schema_score']:.0f}" if r['schema_score'] is not None else 'N/A'
        extraction = f"{r['extraction_score']:.0f}" if r['extraction_score'] is not None else 'N/A'

        fresh = f"{r['freshness_score']:.0f}" if r['freshness_score'] is not None else 'N/A'
        depth = f"{r['content_depth_score']:.0f}" if r['content_depth_score'] is not None else 'N/A'
        links = f"{r['internal_link_score']:.0f}" if r['internal_link_score'] is not None else 'N/A'
        techseo = f"{r['technical_seo_score']:.0f}" if r['technical_seo_score'] is not None else 'N/A'

        out.append(f'## {i}. {r["title"]}')
        out.append(f'- URL: {r["url"]}')
        out.append(f'- Words: {r["word_count"]} | Intent: {intent} | Meta desc: {has_meta}')
        out.append(f'- Health: **{health}/100** | Role: {role} | Trend: {trend}')
        out.append(f'- Components: freshness={fresh} depth={depth} links={links} techseo={techseo} pagerank={pagerank}')
        out.append(f'- AI: citability={ai_cite} eeat={eeat} schema={schema} extraction={extraction}')
        out.append('')

    # 4. Clusters with posts
    clusters = await conn.fetch('''
        SELECT c.id, c.label, c.description, c.post_count, c.health_score, c.ecosystem_state,
               c.parent_cluster_id
        FROM clusters c WHERE c.site_id = $1
        ORDER BY c.post_count DESC NULLS LAST
    ''', SITE_ID)
    out.append(f'\n# TOPIC CLUSTERS ({len(clusters)} total)')
    out.append('')
    for c in clusters:
        parent = f' (sub-cluster of {c["parent_cluster_id"]})' if c["parent_cluster_id"] else ''
        health = f'{c["health_score"]:.0f}' if c["health_score"] else 'N/A'
        out.append(f'## {c["label"]}{parent}')
        out.append(f'- Posts: {c["post_count"]} | Health: {health} | State: {c["ecosystem_state"]}')
        out.append(f'- Description: {c["description"] or "N/A"}')

        cposts = await conn.fetch('''
            SELECT p.title, p.word_count, phs.composite_score
            FROM posts p
            JOIN post_clusters pc ON p.id = pc.post_id
            LEFT JOIN post_health_scores phs ON p.id = phs.post_id
            WHERE pc.cluster_id = $1
            ORDER BY phs.composite_score DESC NULLS LAST
        ''', c['id'])
        for cp in cposts:
            hs = f"{cp['composite_score']:.0f}" if cp['composite_score'] is not None else '?'
            out.append(f'  - [{hs}/100] {cp["title"][:70]} ({cp["word_count"]}w)')
        out.append('')

    # 5. Cannibalization pairs (ALL)
    cpairs = await conn.fetch('''
        SELECT p1.title as a_title, p1.url as a_url,
               p2.title as b_title, p2.url as b_url,
               cp.cosine_similarity, cp.overlap_score, cp.severity
        FROM cannibalization_pairs cp
        JOIN posts p1 ON cp.post_a_id = p1.id
        JOIN posts p2 ON cp.post_b_id = p2.id
        WHERE p1.site_id = $1
        ORDER BY cp.cosine_similarity DESC
    ''', SITE_ID)
    out.append(f'\n# CANNIBALIZATION PAIRS ({len(cpairs)} total)')
    out.append('')
    for cp in cpairs:
        overlap = f"{cp['overlap_score']:.3f}" if cp['overlap_score'] else 'N/A'
        out.append(f'- [{cp["severity"]}] cosine={cp["cosine_similarity"]:.3f} overlap={overlap}')
        out.append(f'  A: {cp["a_title"][:65]}')
        out.append(f'  B: {cp["b_title"][:65]}')

    # 6. Content problems
    probs = await conn.fetch('''
        SELECT cp.problem_type, cp.severity, p.title, p.url, cp.details
        FROM content_problems cp
        JOIN posts p ON cp.post_id = p.id
        WHERE p.site_id = $1
        ORDER BY CASE cp.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                 cp.problem_type
    ''', SITE_ID)
    out.append(f'\n# CONTENT PROBLEMS ({len(probs)} total)')
    out.append('')
    for pr in probs:
        details = json.loads(pr['details']) if pr['details'] else {}
        detail_str = json.dumps(details, indent=None)[:150]
        out.append(f'- [{pr["severity"]}] **{pr["problem_type"]}**: {pr["title"][:60]}')
        out.append(f'  URL: {pr["url"]}')
        out.append(f'  Details: {detail_str}')

    # 7. Recommendations (ALL)
    recs = await conn.fetch('''
        SELECT r.recommendation_type, r.priority, r.title, r.summary,
               r.specific_actions, r.estimated_effort_hours, r.estimated_impact,
               p.title as post_title, p.url as post_url
        FROM recommendations r
        JOIN posts p ON r.post_id = p.id
        WHERE r.site_id = $1
        ORDER BY CASE r.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                 r.recommendation_type
    ''', SITE_ID)
    out.append(f'\n# RECOMMENDATIONS ({len(recs)} total)')
    out.append('')
    for rec in recs:
        actions = json.loads(rec['specific_actions']) if rec['specific_actions'] else []
        action_str = '; '.join(str(a)[:80] for a in actions[:3]) if actions else 'none'
        out.append(f'- [{rec["priority"]}] **{rec["recommendation_type"]}**: {rec["post_title"][:55]}')
        out.append(f'  Title: {rec["title"]}')
        out.append(f'  Summary: {(rec["summary"] or "")[:200]}')
        out.append(f'  Impact: {rec["estimated_impact"]} | Effort: {rec["estimated_effort_hours"]}h')
        out.append(f'  Actions: {action_str}')

    # 8. Aggregate stats
    out.append(f'\n# AGGREGATE STATISTICS')
    out.append('')

    avg_health = await conn.fetchval(
        'SELECT avg(composite_score) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1',
        SITE_ID
    ) or 0
    out.append(f'Overall health score: {avg_health:.1f}/100')

    role_counts = await conn.fetch(
        'SELECT role, count(*) as c FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1 GROUP BY role ORDER BY c DESC',
        SITE_ID
    )
    out.append(f'Role distribution:')
    for rc in role_counts:
        out.append(f'  {rc["role"]}: {rc["c"]} posts')

    intent_counts = await conn.fetch(
        'SELECT content_intent, count(*) as c FROM posts WHERE site_id = $1 GROUP BY content_intent ORDER BY c DESC',
        SITE_ID
    )
    out.append(f'Intent distribution:')
    for ic in intent_counts:
        out.append(f'  {ic["content_intent"]}: {ic["c"]} posts')

    cann_post_count = await conn.fetchval('''
        SELECT COUNT(DISTINCT post_id) FROM (
            SELECT cp.post_a_id AS post_id FROM cannibalization_pairs cp
            JOIN clusters cl ON cl.id = cp.cluster_id WHERE cl.site_id = $1
            UNION
            SELECT cp.post_b_id AS post_id FROM cannibalization_pairs cp
            JOIN clusters cl ON cl.id = cp.cluster_id WHERE cl.site_id = $1
        ) sub
    ''', SITE_ID)
    out.append(f'Cannibalization: {cann_post_count} of {post_count} posts involved in {len(cpairs)} pairs')

    prob_summary = await conn.fetch('''
        SELECT problem_type, count(*) as c FROM content_problems cp
        JOIN posts p ON cp.post_id = p.id WHERE p.site_id = $1
        GROUP BY problem_type ORDER BY c DESC
    ''', SITE_ID)
    out.append(f'Problems by type:')
    for ps in prob_summary:
        out.append(f'  {ps["problem_type"]}: {ps["c"]}')

    rec_summary = await conn.fetch('''
        SELECT recommendation_type, count(*) as c FROM recommendations
        WHERE site_id = $1 GROUP BY recommendation_type ORDER BY c DESC
    ''', SITE_ID)
    out.append(f'Recommendations by type:')
    for rs in rec_summary:
        out.append(f'  {rs["recommendation_type"]}: {rs["c"]}')

    ai = await conn.fetchrow('''
        SELECT avg(ai_citability_score) as cite, avg(eeat_score) as eeat,
               avg(schema_score) as schema, avg(extraction_score) as extract,
               count(*) filter (where ai_citability_score >= 60) as ready,
               count(*) filter (where ai_citability_score is not null) as total_scored
        FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id
        WHERE p.site_id = $1 AND ai_citability_score IS NOT NULL
    ''', SITE_ID)
    if ai and ai['total_scored']:
        pct = ai['ready'] / ai['total_scored'] * 100
        out.append(f'AI Readiness:')
        out.append(f'  Citability: {ai["cite"]:.1f}/100')
        out.append(f'  E-E-A-T: {ai["eeat"]:.1f}/100')
        out.append(f'  Schema: {ai["schema"]:.1f}/100')
        out.append(f'  Extraction: {ai["extract"]:.1f}/100')
        out.append(f'  AI-ready posts: {ai["ready"]}/{ai["total_scored"]} ({pct:.1f}%)')

    # Health score distribution
    dist = await conn.fetch('''
        SELECT
            CASE
                WHEN composite_score >= 80 THEN '80-100 (excellent)'
                WHEN composite_score >= 65 THEN '65-79 (good)'
                WHEN composite_score >= 40 THEN '40-64 (moderate)'
                WHEN composite_score >= 20 THEN '20-39 (poor)'
                ELSE '0-19 (critical)'
            END as bucket,
            count(*) as c
        FROM post_health_scores phs
        JOIN posts p ON p.id = phs.post_id
        WHERE p.site_id = $1
        GROUP BY bucket ORDER BY bucket
    ''', SITE_ID)
    out.append(f'Health score distribution:')
    for d in dist:
        out.append(f'  {d["bucket"]}: {d["c"]} posts')

    sys.stdout.buffer.write('\n'.join(out).encode('utf-8', errors='replace'))
    await conn.close()


if __name__ == '__main__':
    site_id = sys.argv[1] if len(sys.argv) > 1 else '30fb54bc-6247-4bc2-9766-c75d03cd150a'
    asyncio.run(dump(site_id))
