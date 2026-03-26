"""Depth verification queries for cookieandkate.com.

Answers every gap identified in the review:
1. One complete recommendation (all fields)
2. One complete health score breakdown (all factors)
3. Post-to-cluster integrity check
4. Cannibalization similarity distribution (full shape)
5. Cluster semantic coherence (largest cluster post titles)
6. Overlap_score vs cosine_similarity check
"""
import asyncio
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncpg

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/enough')
SITE_ID = uuid.UUID('30fb54bc-6247-4bc2-9766-c75d03cd150a')


async def run():
    conn = await asyncpg.connect(DB_URL)
    out = []

    # ════════════════════════════════════════════════════════════
    # 1. ONE COMPLETE RECOMMENDATION (all fields)
    # ════════════════════════════════════════════════════════════
    out.append("=" * 80)
    out.append("1. COMPLETE RECOMMENDATION (highest priority, all fields)")
    out.append("=" * 80)

    rec = await conn.fetchrow("""
        SELECT r.*, p.title as post_title, p.url as post_url, p.word_count
        FROM recommendations r
        JOIN posts p ON r.post_id = p.id
        WHERE r.site_id = $1
        ORDER BY CASE r.priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                 r.created_at ASC
        LIMIT 1
    """, SITE_ID)
    if rec:
        for k in rec.keys():
            val = rec[k]
            if isinstance(val, (dict, list)):
                val = json.dumps(val, indent=2, default=str)
            elif isinstance(val, str) and len(val) > 200:
                # Try to parse as JSON for pretty printing
                try:
                    parsed = json.loads(val)
                    val = json.dumps(parsed, indent=2, default=str)
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(f"  {k}: {val}")
    else:
        out.append("  NO RECOMMENDATIONS FOUND")

    # Also get a differentiate rec (the most common type)
    out.append("")
    out.append("-" * 40)
    out.append("ALSO: One differentiate recommendation (most common type)")
    out.append("-" * 40)
    diff_rec = await conn.fetchrow("""
        SELECT r.*, p.title as post_title, p.url as post_url
        FROM recommendations r
        JOIN posts p ON r.post_id = p.id
        WHERE r.site_id = $1 AND r.recommendation_type = 'differentiate'
        ORDER BY r.created_at ASC
        LIMIT 1
    """, SITE_ID)
    if diff_rec:
        for k in diff_rec.keys():
            val = diff_rec[k]
            if isinstance(val, (dict, list)):
                val = json.dumps(val, indent=2, default=str)
            elif isinstance(val, str) and len(val) > 200:
                try:
                    parsed = json.loads(val)
                    val = json.dumps(parsed, indent=2, default=str)
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(f"  {k}: {val}")

    # Also an optimize rec
    out.append("")
    out.append("-" * 40)
    out.append("ALSO: One optimize recommendation")
    out.append("-" * 40)
    opt_rec = await conn.fetchrow("""
        SELECT r.*, p.title as post_title, p.url as post_url
        FROM recommendations r
        JOIN posts p ON r.post_id = p.id
        WHERE r.site_id = $1 AND r.recommendation_type = 'optimize'
        ORDER BY r.created_at ASC
        LIMIT 1
    """, SITE_ID)
    if opt_rec:
        for k in opt_rec.keys():
            val = opt_rec[k]
            if isinstance(val, (dict, list)):
                val = json.dumps(val, indent=2, default=str)
            elif isinstance(val, str) and len(val) > 200:
                try:
                    parsed = json.loads(val)
                    val = json.dumps(parsed, indent=2, default=str)
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(f"  {k}: {val}")

    # ════════════════════════════════════════════════════════════
    # 2. COMPLETE HEALTH SCORE BREAKDOWN (one post, all columns)
    # ════════════════════════════════════════════════════════════
    out.append("")
    out.append("=" * 80)
    out.append("2. COMPLETE HEALTH SCORE BREAKDOWN (top-scoring post)")
    out.append("=" * 80)

    # Get the top post
    top_post = await conn.fetchrow("""
        SELECT p.id, p.title, p.url, p.word_count, p.content_intent, p.meta_description IS NOT NULL as has_meta
        FROM posts p
        JOIN post_health_scores phs ON p.id = phs.post_id
        WHERE p.site_id = $1
        ORDER BY phs.composite_score DESC
        LIMIT 1
    """, SITE_ID)
    if top_post:
        out.append(f"  Post: {top_post['title']}")
        out.append(f"  URL: {top_post['url']}")
        out.append(f"  Words: {top_post['word_count']} | Intent: {top_post['content_intent']} | Has meta: {top_post['has_meta']}")
        out.append("")

    # Dump ALL columns from post_health_scores
    hs = await conn.fetchrow("""
        SELECT * FROM post_health_scores WHERE post_id = $1
    """, top_post['id'])
    if hs:
        out.append("  ALL post_health_scores columns:")
        for k in hs.keys():
            out.append(f"    {k}: {hs[k]}")

    # Also dump the worst post's health score
    out.append("")
    out.append("-" * 40)
    out.append("ALSO: Worst post health score breakdown")
    out.append("-" * 40)
    worst_post = await conn.fetchrow("""
        SELECT p.id, p.title, p.word_count
        FROM posts p JOIN post_health_scores phs ON p.id = phs.post_id
        WHERE p.site_id = $1
        ORDER BY phs.composite_score ASC
        LIMIT 1
    """, SITE_ID)
    if worst_post:
        out.append(f"  Post: {worst_post['title']} ({worst_post['word_count']}w)")
        ws = await conn.fetchrow("SELECT * FROM post_health_scores WHERE post_id = $1", worst_post['id'])
        if ws:
            for k in ws.keys():
                out.append(f"    {k}: {ws[k]}")

    # ════════════════════════════════════════════════════════════
    # 3. POST-TO-CLUSTER INTEGRITY CHECK
    # ════════════════════════════════════════════════════════════
    out.append("")
    out.append("=" * 80)
    out.append("3. POST-TO-CLUSTER INTEGRITY CHECK")
    out.append("=" * 80)

    total_posts = await conn.fetchval("SELECT COUNT(*) FROM posts WHERE site_id = $1", SITE_ID)
    distinct_assigned = await conn.fetchval("""
        SELECT COUNT(DISTINCT pc.post_id) FROM post_clusters pc
        JOIN posts p ON p.id = pc.post_id WHERE p.site_id = $1
    """, SITE_ID)
    total_assignments = await conn.fetchval("""
        SELECT COUNT(*) FROM post_clusters pc
        JOIN posts p ON p.id = pc.post_id WHERE p.site_id = $1
    """, SITE_ID)
    multi_assigned = await conn.fetchval("""
        SELECT COUNT(*) FROM (
            SELECT pc.post_id, COUNT(*) as cluster_count
            FROM post_clusters pc JOIN posts p ON p.id = pc.post_id
            WHERE p.site_id = $1
            GROUP BY pc.post_id HAVING COUNT(*) > 1
        ) sub
    """, SITE_ID)
    unassigned = await conn.fetchval("""
        SELECT COUNT(*) FROM posts p
        WHERE p.site_id = $1
        AND p.id NOT IN (SELECT post_id FROM post_clusters pc2
                         JOIN posts p2 ON p2.id = pc2.post_id WHERE p2.site_id = $1)
    """, SITE_ID)

    out.append(f"  Total posts:              {total_posts}")
    out.append(f"  Distinct posts assigned:  {distinct_assigned}")
    out.append(f"  Total assignments:        {total_assignments} (post_clusters rows)")
    out.append(f"  Multi-assigned posts:     {multi_assigned} (in >1 cluster)")
    out.append(f"  Unassigned posts:         {unassigned} (in 0 clusters)")
    out.append(f"  Ratio:                    {total_assignments}/{total_posts} = {total_assignments/total_posts:.2f}x")

    if multi_assigned > 0:
        multi_rows = await conn.fetch("""
            SELECT p.title, COUNT(*) as cluster_count,
                   array_agg(c.label) as cluster_labels
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            JOIN clusters c ON c.id = pc.cluster_id
            WHERE p.site_id = $1
            GROUP BY p.id, p.title HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC LIMIT 10
        """, SITE_ID)
        out.append(f"\n  Multi-assigned posts (top 10):")
        for mr in multi_rows:
            out.append(f"    [{mr['cluster_count']} clusters] {mr['title'][:55]} → {mr['cluster_labels']}")

    if unassigned > 0:
        urows = await conn.fetch("""
            SELECT p.title FROM posts p
            WHERE p.site_id = $1
            AND p.id NOT IN (SELECT post_id FROM post_clusters)
            LIMIT 10
        """, SITE_ID)
        out.append(f"\n  Unassigned posts:")
        for u in urows:
            out.append(f"    {u['title']}")

    # Cluster post_count column vs actual post_clusters count
    out.append("")
    out.append("  Cluster post_count column vs actual assignments:")
    cluster_check = await conn.fetch("""
        SELECT c.label, c.post_count as stored_count,
               (SELECT COUNT(*) FROM post_clusters pc WHERE pc.cluster_id = c.id) as actual_count
        FROM clusters c WHERE c.site_id = $1
        ORDER BY c.post_count DESC NULLS LAST
    """, SITE_ID)
    for cc in cluster_check:
        match = "OK" if cc['stored_count'] == cc['actual_count'] else f"MISMATCH ({cc['stored_count']} stored vs {cc['actual_count']} actual)"
        out.append(f"    {cc['label'][:40]}: stored={cc['stored_count']} actual={cc['actual_count']} → {match}")

    # ════════════════════════════════════════════════════════════
    # 4. CANNIBALIZATION SIMILARITY DISTRIBUTION (full shape)
    # ════════════════════════════════════════════════════════════
    out.append("")
    out.append("=" * 80)
    out.append("4. CANNIBALIZATION SIMILARITY DISTRIBUTION")
    out.append("=" * 80)

    # Percentiles
    pctiles = await conn.fetchrow("""
        SELECT
            COUNT(*) as total,
            MIN(cp.cosine_similarity) as min_sim,
            percentile_cont(0.05) WITHIN GROUP (ORDER BY cp.cosine_similarity) as p5,
            percentile_cont(0.10) WITHIN GROUP (ORDER BY cp.cosine_similarity) as p10,
            percentile_cont(0.25) WITHIN GROUP (ORDER BY cp.cosine_similarity) as p25,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY cp.cosine_similarity) as p50,
            percentile_cont(0.75) WITHIN GROUP (ORDER BY cp.cosine_similarity) as p75,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY cp.cosine_similarity) as p90,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY cp.cosine_similarity) as p95,
            MAX(cp.cosine_similarity) as max_sim,
            AVG(cp.cosine_similarity) as avg_sim,
            STDDEV(cp.cosine_similarity) as stddev_sim
        FROM cannibalization_pairs cp
        JOIN posts p1 ON cp.post_a_id = p1.id
        WHERE p1.site_id = $1
    """, SITE_ID)
    out.append(f"  Total pairs: {pctiles['total']}")
    out.append(f"  Min:    {pctiles['min_sim']:.4f}")
    out.append(f"  P5:     {pctiles['p5']:.4f}")
    out.append(f"  P10:    {pctiles['p10']:.4f}")
    out.append(f"  P25:    {pctiles['p25']:.4f}")
    out.append(f"  Median: {pctiles['p50']:.4f}")
    out.append(f"  P75:    {pctiles['p75']:.4f}")
    out.append(f"  P90:    {pctiles['p90']:.4f}")
    out.append(f"  P95:    {pctiles['p95']:.4f}")
    out.append(f"  Max:    {pctiles['max_sim']:.4f}")
    out.append(f"  Mean:   {pctiles['avg_sim']:.4f}")
    out.append(f"  StdDev: {pctiles['stddev_sim']:.4f}")

    # What's at specific positions?
    out.append("")
    out.append("  Pairs at specific positions (sorted by cosine DESC):")
    for pos in [1, 10, 50, 100, 150, 200, 250, 300]:
        row = await conn.fetchrow("""
            SELECT p1.title as a, p2.title as b, cp.cosine_similarity
            FROM cannibalization_pairs cp
            JOIN posts p1 ON cp.post_a_id = p1.id
            JOIN posts p2 ON cp.post_b_id = p2.id
            WHERE p1.site_id = $1
            ORDER BY cp.cosine_similarity DESC
            OFFSET $2 LIMIT 1
        """, SITE_ID, pos - 1)
        if row:
            out.append(f"    #{pos}: {row['cosine_similarity']:.4f} — {row['a'][:35]} ↔ {row['b'][:35]}")

    # Bucket distribution
    out.append("")
    out.append("  Distribution by 0.01 buckets:")
    buckets = await conn.fetch("""
        SELECT ROUND(cp.cosine_similarity::numeric, 2) as bucket, COUNT(*) as cnt
        FROM cannibalization_pairs cp
        JOIN posts p1 ON cp.post_a_id = p1.id
        WHERE p1.site_id = $1
        GROUP BY bucket ORDER BY bucket DESC
    """, SITE_ID)
    for b in buckets:
        bar = "#" * b['cnt']
        out.append(f"    {b['bucket']}: {b['cnt']:3d} {bar}")

    # ════════════════════════════════════════════════════════════
    # 5. CLUSTER SEMANTIC COHERENCE (largest cluster)
    # ════════════════════════════════════════════════════════════
    out.append("")
    out.append("=" * 80)
    out.append("5. CLUSTER SEMANTIC COHERENCE")
    out.append("=" * 80)

    # Get all clusters, show all posts in the top 3
    top_clusters = await conn.fetch("""
        SELECT c.id, c.label, c.post_count
        FROM clusters c WHERE c.site_id = $1
        ORDER BY c.post_count DESC LIMIT 3
    """, SITE_ID)
    for tc in top_clusters:
        out.append(f"\n  Cluster: {tc['label']} ({tc['post_count']} posts)")
        out.append(f"  {'─' * 60}")
        posts_in = await conn.fetch("""
            SELECT p.title, p.word_count, p.content_intent
            FROM posts p JOIN post_clusters pc ON p.id = pc.post_id
            WHERE pc.cluster_id = $1
            ORDER BY p.word_count DESC
        """, tc['id'])
        for pi in posts_in:
            out.append(f"    [{pi['content_intent']}] {pi['title'][:65]} ({pi['word_count']}w)")

    # ════════════════════════════════════════════════════════════
    # 6. OVERLAP_SCORE vs COSINE_SIMILARITY CHECK
    # ════════════════════════════════════════════════════════════
    out.append("")
    out.append("=" * 80)
    out.append("6. OVERLAP_SCORE vs COSINE_SIMILARITY")
    out.append("=" * 80)

    # Check if they're always identical
    diff_count = await conn.fetchval("""
        SELECT COUNT(*) FROM cannibalization_pairs cp
        JOIN posts p1 ON cp.post_a_id = p1.id
        WHERE p1.site_id = $1
        AND cp.overlap_score IS NOT NULL
        AND ABS(cp.overlap_score - cp.cosine_similarity) > 0.001
    """, SITE_ID)
    same_count = await conn.fetchval("""
        SELECT COUNT(*) FROM cannibalization_pairs cp
        JOIN posts p1 ON cp.post_a_id = p1.id
        WHERE p1.site_id = $1
        AND cp.overlap_score IS NOT NULL
        AND ABS(cp.overlap_score - cp.cosine_similarity) <= 0.001
    """, SITE_ID)
    null_overlap = await conn.fetchval("""
        SELECT COUNT(*) FROM cannibalization_pairs cp
        JOIN posts p1 ON cp.post_a_id = p1.id
        WHERE p1.site_id = $1 AND cp.overlap_score IS NULL
    """, SITE_ID)
    out.append(f"  Pairs where overlap_score = cosine_similarity: {same_count}")
    out.append(f"  Pairs where they differ (>0.001):              {diff_count}")
    out.append(f"  Pairs where overlap_score is NULL:             {null_overlap}")
    out.append(f"  VERDICT: {'IDENTICAL — overlap_score is just a copy of cosine_similarity' if diff_count == 0 and null_overlap == 0 else 'DIFFERENT' if diff_count > 0 else 'PARTIALLY NULL'}")

    # Check what other columns exist in cannibalization_pairs
    out.append("")
    out.append("  All columns in cannibalization_pairs (sample row):")
    sample_cp = await conn.fetchrow("""
        SELECT * FROM cannibalization_pairs cp
        JOIN posts p1 ON cp.post_a_id = p1.id
        WHERE p1.site_id = $1 LIMIT 1
    """, SITE_ID)
    if sample_cp:
        for k in sample_cp.keys():
            if k not in ('body_text', 'meta_description', 'content_hash'):
                val = sample_cp[k]
                if isinstance(val, str) and len(str(val)) > 100:
                    val = str(val)[:100] + "..."
                out.append(f"    {k}: {val}")

    # ════════════════════════════════════════════════════════════
    # 7. HEALTH SCORING WEIGHT VERIFICATION
    # ════════════════════════════════════════════════════════════
    out.append("")
    out.append("=" * 80)
    out.append("7. HEALTH SCORING — WEIGHT SUM AND FACTOR CONTRIBUTION CHECK")
    out.append("=" * 80)

    # Get the middle-scoring post for a balanced view
    mid_post = await conn.fetchrow("""
        SELECT p.id, p.title, p.word_count, phs.*
        FROM posts p JOIN post_health_scores phs ON p.id = phs.post_id
        WHERE p.site_id = $1
        ORDER BY ABS(phs.composite_score - 41)  -- closest to average
        LIMIT 1
    """, SITE_ID)
    if mid_post:
        out.append(f"  Post: {mid_post['title']} ({mid_post['word_count']}w)")
        out.append(f"  Composite: {mid_post['composite_score']}")
        out.append("")
        # List all numeric factor columns
        factor_cols = [k for k in mid_post.keys() if k.endswith('_score') and k != 'composite_score' and mid_post[k] is not None]
        out.append(f"  Factor scores present: {factor_cols}")
        for fc in factor_cols:
            out.append(f"    {fc}: {mid_post[fc]}")

    text = "\n".join(out)
    sys.stdout.buffer.write(text.encode('utf-8', errors='replace'))
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
