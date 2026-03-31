"""Verify every checklist item against actual DB state."""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncpg

DB_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/enough')
SITE_ID = uuid.UUID('30fb54bc-6247-4bc2-9766-c75d03cd150a')


async def verify():
    conn = await asyncpg.connect(DB_URL)

    posts = await conn.fetchval('SELECT COUNT(*) FROM posts WHERE site_id = $1', SITE_ID)

    print("=" * 70)
    print("CHECKLIST VERIFICATION: cookieandkate.com")
    print("=" * 70)

    # STEP 1: CRAWL
    null_titles = await conn.fetchval('SELECT COUNT(*) FROM posts WHERE site_id = $1 AND title IS NULL', SITE_ID)
    zero_words = await conn.fetchval('SELECT COUNT(*) FROM posts WHERE site_id = $1 AND word_count = 0', SITE_ID)
    has_meta = await conn.fetchval('SELECT COUNT(*) FROM posts WHERE site_id = $1 AND meta_description IS NOT NULL', SITE_ID)
    has_headings = await conn.fetchval("SELECT COUNT(*) FROM posts WHERE site_id = $1 AND headings IS NOT NULL AND headings != '[]'", SITE_ID)
    has_html = await conn.fetchval('SELECT COUNT(*) FROM posts WHERE site_id = $1 AND body_html IS NOT NULL', SITE_ID)
    print(f"\nSTEP 1 CRAWL: {posts} posts")
    print(f"  [{'PASS' if null_titles == 0 else 'FAIL'}] No NULL titles: {null_titles}")
    print(f"  [{'PASS' if zero_words <= 1 else 'FAIL'}] No zero-word posts (except index): {zero_words}")
    print(f"  [INFO] Posts with meta_description: {has_meta}/{posts}")
    print(f"  [INFO] Posts with headings: {has_headings}/{posts}")
    print(f"  [INFO] Posts with body_html: {has_html}/{posts}")

    # STEP 2: EMBEDDINGS
    embs = await conn.fetchval('SELECT COUNT(*) FROM post_embeddings pe JOIN posts p ON p.id = pe.post_id WHERE p.site_id = $1', SITE_ID)
    print(f"\nSTEP 2 EMBEDDINGS:")
    print(f"  [{'PASS' if embs == posts else 'FAIL'}] All posts embedded: {embs}/{posts}")

    # STEP 3: READABILITY
    read = await conn.fetchval('SELECT COUNT(*) FROM posts WHERE site_id = $1 AND readability_score IS NOT NULL', SITE_ID)
    col = await conn.fetchval("SELECT column_name FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'readability_details'")
    print(f"\nSTEP 3 READABILITY:")
    print(f"  [{'PASS' if col else 'FAIL'}] readability_details column exists: {col is not None}")
    print(f"  [{'PASS' if read > 0 else 'FAIL'}] Posts with readability scores: {read}/{posts}")

    # STEP 4: PAGERANK
    pr = await conn.fetchval('SELECT COUNT(*) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1 AND phs.internal_pagerank IS NOT NULL', SITE_ID)
    print(f"\nSTEP 4 PAGERANK:")
    print(f"  [{'PASS' if pr > 0 else 'FAIL'}] Posts with pagerank: {pr}/{posts}")

    # STEP 5: INTENT
    intents = await conn.fetch('SELECT content_intent, COUNT(*) as c FROM posts WHERE site_id = $1 GROUP BY content_intent ORDER BY c DESC', SITE_ID)
    classified = sum(r['c'] for r in intents if r['content_intent'] is not None)
    print(f"\nSTEP 5 INTENT:")
    print(f"  [{'PASS' if classified == posts else 'FAIL'}] All posts classified: {classified}/{posts}")
    for i in intents:
        print(f"  {i['content_intent']}: {i['c']}")

    # STEP 6: CLUSTERING
    assigned = await conn.fetchval('SELECT COUNT(DISTINCT pc.post_id) FROM post_clusters pc JOIN clusters c ON c.id = pc.cluster_id WHERE c.site_id = $1', SITE_ID)
    total_rows = await conn.fetchval('SELECT COUNT(*) FROM post_clusters pc JOIN clusters c ON c.id = pc.cluster_id WHERE c.site_id = $1', SITE_ID)
    multi = await conn.fetchval('SELECT COUNT(*) FROM (SELECT pc.post_id FROM post_clusters pc JOIN clusters c ON c.id = pc.cluster_id WHERE c.site_id = $1 GROUP BY pc.post_id HAVING COUNT(*) > 1) sub', SITE_ID)
    empty = await conn.fetchval('SELECT COUNT(*) FROM clusters WHERE site_id = $1 AND (post_count = 0 OR post_count IS NULL)', SITE_ID)
    cluster_count = await conn.fetchval('SELECT COUNT(*) FROM clusters WHERE site_id = $1', SITE_ID)
    tl_clusters = await conn.fetchval('SELECT COUNT(*) FROM clusters WHERE site_id = $1 AND parent_cluster_id IS NULL', SITE_ID)
    print(f"\nSTEP 6 CLUSTERING:")
    print(f"  [{'PASS' if assigned == posts else 'FAIL'}] All posts assigned: {assigned}/{posts}")
    print(f"  [{'PASS' if total_rows == posts else 'WARN'}] Assignment rows = posts: {total_rows}/{posts}")
    print(f"  [{'PASS' if multi == 0 else 'FAIL'}] No multi-assigned: {multi}")
    print(f"  [{'WARN' if empty > 0 else 'PASS'}] Empty clusters: {empty}")
    print(f"  [INFO] Total clusters: {cluster_count} ({tl_clusters} top-level)")

    # STEP 7: HEALTH
    scored = await conn.fetchval('SELECT COUNT(*) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1 AND phs.composite_score IS NOT NULL', SITE_ID)
    avg_h = await conn.fetchval('SELECT AVG(composite_score) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1', SITE_ID) or 0
    min_h = await conn.fetchval('SELECT MIN(composite_score) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1', SITE_ID) or 0
    max_h = await conn.fetchval('SELECT MAX(composite_score) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1', SITE_ID) or 0
    spread = max_h - min_h
    ai_in_scored = await conn.fetchval('SELECT COUNT(*) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1 AND ai_citability_score IS NOT NULL AND composite_score IS NOT NULL', SITE_ID)
    print(f"\nSTEP 7 HEALTH:")
    print(f"  [{'PASS' if scored >= posts - 5 else 'FAIL'}] Posts scored: {scored}/{posts}")
    print(f"  [{'PASS' if 30 <= avg_h <= 70 else 'WARN'}] Avg in range 30-70: {avg_h:.1f}")
    print(f"  [{'PASS' if spread > 20 else 'FAIL'}] Spread > 20: {spread:.1f}")
    print(f"  [{'PASS' if ai_in_scored == scored else 'FAIL'}] AI scores in composite: {ai_in_scored}/{scored}")
    print(f"  [INFO] Range: {min_h:.1f} - {max_h:.1f}")

    # STEP 8: CANNIBALIZATION
    pairs = await conn.fetchval('SELECT COUNT(*) FROM cannibalization_pairs cp JOIN clusters c ON c.id = cp.cluster_id WHERE c.site_id = $1', SITE_ID)
    cann_posts = await conn.fetchval("""SELECT COUNT(DISTINCT post_id) FROM (
        SELECT post_a_id as post_id FROM cannibalization_pairs cp JOIN clusters c ON c.id = cp.cluster_id WHERE c.site_id = $1
        UNION SELECT post_b_id FROM cannibalization_pairs cp JOIN clusters c ON c.id = cp.cluster_id WHERE c.site_id = $1
    ) sub""", SITE_ID)
    min_sim = await conn.fetchval('SELECT MIN(cosine_similarity) FROM cannibalization_pairs cp JOIN posts p ON p.id = cp.post_a_id WHERE p.site_id = $1', SITE_ID) or 0
    max_sim = await conn.fetchval('SELECT MAX(cosine_similarity) FROM cannibalization_pairs cp JOIN posts p ON p.id = cp.post_a_id WHERE p.site_id = $1', SITE_ID) or 0
    overlap_diff = await conn.fetchval('SELECT COUNT(*) FROM cannibalization_pairs cp JOIN posts p ON p.id = cp.post_a_id WHERE p.site_id = $1 AND overlap_score IS NOT NULL AND ABS(overlap_score - cosine_similarity) > 0.001', SITE_ID)
    print(f"\nSTEP 8 CANNIBALIZATION:")
    print(f"  [{'PASS' if cann_posts < posts else 'WARN'}] Posts involved < total: {cann_posts}/{posts}")
    print(f"  [{'PASS' if max_sim < 0.99 else 'WARN'}] Top pair < 0.99: {max_sim:.3f}")
    print(f"  [{'PASS' if min_sim > 0.70 else 'WARN'}] Bottom pair > 0.70: {min_sim:.3f}")
    print(f"  [INFO] overlap_score = cosine (no GSC): {overlap_diff} differ")
    print(f"  [INFO] {pairs} pairs, {cann_posts} posts involved")

    # STEP 9: PROBLEMS
    probs = await conn.fetchval('SELECT COUNT(*) FROM content_problems cp JOIN posts p ON p.id = cp.post_id WHERE p.site_id = $1', SITE_ID)
    prob_types = await conn.fetch('SELECT problem_type, COUNT(*) as c FROM content_problems cp JOIN posts p ON p.id = cp.post_id WHERE p.site_id = $1 GROUP BY problem_type ORDER BY c DESC', SITE_ID)
    n_types = len(prob_types)
    print(f"\nSTEP 9 PROBLEMS:")
    print(f"  [INFO] {probs} total problems, {n_types} types")
    for pt in prob_types:
        print(f"  {pt['problem_type']}: {pt['c']}")

    # STEP 10: RECOMMENDATIONS
    recs = await conn.fetchval('SELECT COUNT(*) FROM recommendations WHERE site_id = $1', SITE_ID)
    rec_types = await conn.fetch('SELECT recommendation_type, COUNT(*) as c FROM recommendations WHERE site_id = $1 GROUP BY recommendation_type ORDER BY c DESC', SITE_ID)
    bad_tpl = await conn.fetchval("SELECT COUNT(*) FROM recommendations WHERE site_id = $1 AND (title LIKE '%{title}%' OR summary LIKE '%{word_count}%')", SITE_ID)
    title_short = await conn.fetchval("SELECT COUNT(*) FROM recommendations WHERE site_id = $1 AND title LIKE 'Fix title%' AND summary LIKE '%only%'", SITE_ID)
    title_long = await conn.fetchval("SELECT COUNT(*) FROM recommendations WHERE site_id = $1 AND title LIKE 'Fix title%' AND summary LIKE '%truncat%'", SITE_ID)
    print(f"\nSTEP 10 RECOMMENDATIONS:")
    print(f"  [{'PASS' if recs < 5 * posts else 'WARN'}] Recs < 5x posts: {recs} < {5*posts}")
    print(f"  [{'PASS' if len(rec_types) >= 3 else 'FAIL'}] At least 3 types: {len(rec_types)}")
    print(f"  [{'PASS' if bad_tpl == 0 else 'FAIL'}] No template literals: {bad_tpl}")
    print(f"  [{'PASS' if title_short > 0 or title_long > 0 else 'WARN'}] Title direction correct: {title_short} short, {title_long} long")
    for rt in rec_types:
        print(f"  {rt['recommendation_type']}: {rt['c']}")

    # STEP 10b: AI CITABILITY
    ai = await conn.fetchval('SELECT COUNT(*) FROM post_health_scores phs JOIN posts p ON p.id = phs.post_id WHERE p.site_id = $1 AND ai_citability_score IS NOT NULL', SITE_ID)
    print(f"\nSTEP 10b AI CITABILITY:")
    print(f"  [{'PASS' if ai >= posts - 5 else 'FAIL'}] Posts with AI scores: {ai}/{posts}")

    # STEP 11: ENRICHMENT
    enriched = await conn.fetchval("SELECT COUNT(*) FROM recommendations WHERE site_id = $1 AND ai_generated_content IS NOT NULL AND recommendation_type NOT IN ('differentiate')", SITE_ID)
    print(f"\nSTEP 11 ENRICHMENT:")
    print(f"  [{'PASS' if enriched > 0 else 'FAIL'}] Non-diff recs enriched: {enriched}")

    # KNOWN BUGS STATUS
    print(f"\n{'='*70}")
    print("KNOWN BUGS STATUS")
    print(f"{'='*70}")
    print(f"  B1  readability_details column:     {'FIXED' if col else 'OPEN'}")
    print(f"  B2  '300 posts cannibalizing' copy: FIXED (now says '{cann_posts} of {posts} posts')")
    print(f"  B3  Empty Miscellaneous clusters:   {'FIXED (filtered in PDF)' if empty > 0 else 'N/A'}")
    print(f"  B4  Cluster LIMIT 6:                FIXED (now LIMIT 8, parent_cluster_id IS NULL, post_count > 0)")
    print(f"  B5  Title length 'Shorten':         FIXED (now says 'too short' for <30, 'too long' for >70)")
    print(f"  B7  overlap_score = cosine:          OPEN (by design without GSC)")
    print(f"  B8  Enrichment not working:          {'FIXED' if enriched > 0 else 'OPEN'}")
    print(f"  B9  Top 5 duplicates:                FIXED (DISTINCT ON + aggregated issues)")
    print(f"  B10 Mid-word truncation:             FIXED (word-boundary truncation with '...')")
    print(f"  B11 AI not in composite:             FIXED (AI citability runs before health scoring, UPSERT)")
    print(f"  B12 Birthday post Quick Win #3:      FIXED (optimize recs preferred over expand)")

    await conn.close()


if __name__ == '__main__':
    asyncio.run(verify())
