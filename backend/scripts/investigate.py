"""Deep investigation of pipeline data quality issues."""
import asyncio
import json
import os

from dotenv import load_dotenv
load_dotenv()

import asyncpg


async def investigate():
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    sid = "d5f7c8d8-43b8-4518-9698-7f5e7275c7b8"

    print("=== CLUSTERING INTEGRITY ===")
    total_posts = await conn.fetchval("SELECT COUNT(*) FROM posts WHERE site_id = $1", sid)
    distinct_in_clusters = await conn.fetchval(
        "SELECT COUNT(DISTINCT post_id) FROM post_clusters WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)", sid
    )
    multi_cluster_posts = await conn.fetchval("""
        SELECT COUNT(*) FROM (
            SELECT post_id FROM post_clusters
            WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)
            GROUP BY post_id HAVING COUNT(*) > 1
        ) x
    """, sid)
    total_assignments = await conn.fetchval(
        "SELECT COUNT(*) FROM post_clusters WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)", sid
    )
    sum_stored = await conn.fetchval("SELECT COALESCE(SUM(post_count), 0) FROM clusters WHERE site_id = $1", sid)
    cluster_count = await conn.fetchval("SELECT COUNT(*) FROM clusters WHERE site_id = $1", sid)

    print(f"  Total posts: {total_posts}")
    print(f"  Distinct posts in clusters: {distinct_in_clusters}")
    print(f"  Posts NOT in any cluster: {total_posts - distinct_in_clusters}")
    print(f"  Posts in MULTIPLE clusters: {multi_cluster_posts}")
    print(f"  Total assignments (post_clusters rows): {total_assignments}")
    print(f"  Clusters: {cluster_count}")
    print(f"  SUM(clusters.post_count): {sum_stored}")
    print(f"  BUG: {total_assignments} assignments for {total_posts} posts = {total_assignments/total_posts:.1f}x overcounting")

    # Distribution of how many clusters each post is in
    print("\n  Assignments per post:")
    dist = await conn.fetch("""
        SELECT cc, COUNT(*) as posts FROM (
            SELECT post_id, COUNT(*) as cc FROM post_clusters
            WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)
            GROUP BY post_id
        ) x GROUP BY cc ORDER BY cc
    """, sid)
    for d in dist:
        print(f"    In {d['cc']} cluster(s): {d['posts']} posts")

    # Stored vs actual per cluster
    print("\n  Cluster post_count stored vs actual:")
    checks = await conn.fetch("""
        SELECT c.label, c.post_count as stored,
               (SELECT COUNT(*) FROM post_clusters WHERE cluster_id = c.id) as actual
        FROM clusters c WHERE c.site_id = $1 ORDER BY c.post_count DESC
    """, sid)
    for c in checks:
        flag = " MISMATCH" if c["stored"] != c["actual"] else ""
        print(f"    {c['label'][:40]}: stored={c['stored']}, actual={c['actual']}{flag}")

    # Is it parent clusters including children?
    print("\n  Parent/child cluster structure:")
    parents = await conn.fetch("""
        SELECT c.id, c.label, c.post_count, c.parent_cluster_id
        FROM clusters c WHERE c.site_id = $1
        ORDER BY c.parent_cluster_id NULLS FIRST, c.post_count DESC
    """, sid)
    for p in parents:
        parent = "ROOT" if p["parent_cluster_id"] is None else f"child of {str(p['parent_cluster_id'])[:8]}"
        print(f"    {p['label'][:35]} ({p['post_count']} posts) [{parent}]")

    # ======================================
    print("\n=== CANNIBALIZATION ANALYSIS ===")
    total_pairs = await conn.fetchval(
        "SELECT COUNT(*) FROM cannibalization_pairs WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)", sid
    )
    print(f"  Total pairs in DB: {total_pairs}")

    sev = await conn.fetch("""
        SELECT severity, COUNT(*) FROM cannibalization_pairs
        WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)
        GROUP BY severity ORDER BY COUNT(*) DESC
    """, sid)
    for s in sev:
        print(f"  {s['severity']}: {s['count']}")

    cos_dist = await conn.fetch("""
        SELECT
            CASE
                WHEN cosine_similarity >= 0.95 THEN 'A: 0.95+ (near-duplicate)'
                WHEN cosine_similarity >= 0.90 THEN 'B: 0.90-0.95 (very high)'
                WHEN cosine_similarity >= 0.80 THEN 'C: 0.80-0.90 (high)'
                WHEN cosine_similarity >= 0.70 THEN 'D: 0.70-0.80 (moderate)'
                ELSE 'E: below 0.70'
            END as bracket, COUNT(*),
            ROUND(AVG(cosine_similarity)::numeric, 3) as avg
        FROM cannibalization_pairs
        WHERE cluster_id IN (SELECT id FROM clusters WHERE site_id = $1)
        GROUP BY 1 ORDER BY 1
    """, sid)
    print("  Cosine similarity distribution:")
    for c in cos_dist:
        print(f"    {c['bracket']}: {c['count']} pairs (avg {c['avg']})")

    # Is 200 a limit?
    print(f"\n  Is 200 hardcoded? Pairs in DB = {total_pairs}. If exactly 200, yes.")

    # ======================================
    print("\n=== HEALTH SCORE ANALYSIS ===")
    stats = await conn.fetchrow("""
        SELECT COUNT(*) as n,
               ROUND(AVG(composite_score)::numeric, 1) as mean,
               ROUND(STDDEV(composite_score)::numeric, 1) as stddev,
               ROUND(MIN(composite_score)::numeric, 1) as min,
               ROUND(MAX(composite_score)::numeric, 1) as max,
               ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY composite_score)::numeric, 1) as p25,
               ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY composite_score)::numeric, 1) as median,
               ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY composite_score)::numeric, 1) as p75
        FROM post_health_scores
        WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
    """, sid)
    print(f"  Scored: {stats['n']} / {total_posts} posts")
    print(f"  NOT scored: {total_posts - stats['n']}")
    print(f"  Mean: {stats['mean']}, StdDev: {stats['stddev']}")
    print(f"  Min={stats['min']}, P25={stats['p25']}, Median={stats['median']}, P75={stats['p75']}, Max={stats['max']}")
    print(f"  Range: {float(stats['max']) - float(stats['min'])}")

    # Role gap
    print("\n=== ROLE ASSIGNMENT GAP ===")
    total_scored = stats["n"]
    with_role = await conn.fetchval(
        "SELECT COUNT(*) FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1) AND role IS NOT NULL",
        sid,
    )
    print(f"  Scored: {total_scored}")
    print(f"  With role: {with_role}")
    print(f"  Scored but NO role: {total_scored - with_role}")
    print(f"  Not scored at all: {total_posts - total_scored}")
    print(f"  TOTAL MISSING from role assignment: {total_posts - with_role}")

    # Why are some unscored? Check if they're in clusters
    unscored_in_cluster = await conn.fetchval("""
        SELECT COUNT(DISTINCT p.id) FROM posts p
        JOIN post_clusters pc ON pc.post_id = p.id
        JOIN clusters c ON c.id = pc.cluster_id
        WHERE p.site_id = $1
        AND p.id NOT IN (SELECT post_id FROM post_health_scores)
    """, sid)
    unscored_no_cluster = total_posts - stats["n"] - unscored_in_cluster
    print(f"  Unscored but IN a cluster: {unscored_in_cluster}")

    # ======================================
    print("\n=== SAMPLE FULL HEALTH BREAKDOWN (best post) ===")
    best = await conn.fetchrow("""
        SELECT ph.*, p.title, p.word_count, p.url
        FROM post_health_scores ph JOIN posts p ON p.id = ph.post_id
        WHERE p.site_id = $1 ORDER BY ph.composite_score DESC LIMIT 1
    """, sid)
    if best:
        cols = dict(best)
        for k in ["title", "url", "word_count", "composite_score", "role", "trend",
                   "traffic_contribution", "ranking_strength", "engagement_score",
                   "freshness_score", "content_depth_score", "technical_seo_score",
                   "internal_link_score"]:
            if k in cols:
                print(f"  {k}: {cols[k]}")

    # ======================================
    print("\n=== SAMPLE FULL RECOMMENDATION (expand type) ===")
    rec = await conn.fetchrow("""
        SELECT r.*, p.title as post_title, p.word_count, p.url as post_url
        FROM recommendations r JOIN posts p ON p.id = r.post_id
        WHERE r.site_id = $1 AND r.recommendation_type = 'expand'
        ORDER BY p.word_count ASC LIMIT 1
    """, sid)
    if rec:
        print(f"  Type: {rec['recommendation_type']}")
        print(f"  Priority: {rec['priority']}")
        print(f"  Rec title: {rec['title']}")
        print(f"  Post: {rec['post_title']} ({rec['word_count']} words)")
        print(f"  URL: {rec['post_url']}")
        print(f"  Summary: {rec['summary']}")
        actions = rec["specific_actions"]
        if actions:
            acts = json.loads(actions) if isinstance(actions, str) else actions
            if isinstance(acts, list):
                print("  Actions:")
                for a in acts:
                    print(f"    - {a}")
        print(f"  Effort: {rec['estimated_effort_hours']}h")

    # ======================================
    print("\n=== RECOMMENDATION COUNT ANALYSIS ===")
    total_recs = await conn.fetchval("SELECT COUNT(*) FROM recommendations WHERE site_id = $1", sid)
    total_problems = await conn.fetchval("SELECT COUNT(*) FROM content_problems WHERE site_id = $1", sid)
    print(f"  Problems: {total_problems}")
    print(f"  Recommendations: {total_recs}")
    if total_problems:
        print(f"  Ratio: {total_recs / total_problems:.2f}")

    # Check the LIMIT in cannibalization
    print("\n=== CHECKING CANNIBALIZATION PRUNING CODE ===")
    # Just report what we found
    print(f"  Pairs in DB: {total_pairs}")
    print(f"  If both sites have exactly 200, there is a LIMIT 200 somewhere")

    await conn.close()


asyncio.run(investigate())
