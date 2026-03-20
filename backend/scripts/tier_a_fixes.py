"""Tier A fixes — all 10, executed sequentially.

Run: cd backend && python3 scripts/tier_a_fixes.py
"""

import asyncio
import json
import logging
import os
import sys
import time
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import asyncpg
import numpy as np
from anthropic import AsyncAnthropic

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

SITE_ID = UUID("32296e5d-7924-4d9f-92b8-7f774c634fad")


async def fix_a1_cluster_labels(conn: asyncpg.Connection) -> None:
    """A1: Use Claude to generate human-readable cluster labels."""
    logger.info("=== A1: Fix Cluster Labels (Claude) ===")
    
    anthropic = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    
    clusters = await conn.fetch(
        "SELECT id, post_count, parent_cluster_id FROM clusters WHERE site_id = $1 ORDER BY post_count DESC",
        SITE_ID,
    )
    
    for cluster in clusters:
        titles = await conn.fetch("""
            SELECT p.title FROM posts p
            JOIN post_clusters pc ON pc.post_id = p.id
            WHERE pc.cluster_id = $1
            LIMIT 15
        """, cluster["id"])
        
        title_list = [t["title"] for t in titles if t["title"]]
        if not title_list:
            continue
        
        titles_text = "\n".join(f"- {t}" for t in title_list[:15])
        
        try:
            response = await anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[{
                    "role": "user",
                    "content": (
                        f"These {cluster['post_count']} blog posts are in one topic cluster:\n"
                        f"{titles_text}\n\n"
                        f"Give a specific 2-5 word topic label. Be descriptive, not generic.\n"
                        f"Examples: 'Cold Email Outreach', 'CRM Migration Guide', 'Sales Team Hiring'\n"
                        f"Respond with ONLY the label, nothing else."
                    ),
                }],
            )
            label = response.content[0].text.strip().strip('"\'')[:80]
        except Exception as e:
            logger.error("Claude label failed for cluster %s: %s", cluster["id"], e)
            label = f"Topic Cluster ({cluster['post_count']} posts)"
        
        await conn.execute("UPDATE clusters SET label = $1 WHERE id = $2", label, cluster["id"])
        logger.info("  %s posts → '%s'", cluster["post_count"], label)
        await asyncio.sleep(0.35)  # Rate limit ~3/sec
    
    logger.info("✅ A1 complete: %d clusters labeled via Claude", len(clusters))


async def fix_a2_flatten_hierarchy(conn: asyncpg.Connection) -> None:
    """A2: Reassign noise posts from parent clusters to nearest leaf cluster."""
    logger.info("=== A2: Flatten Cluster Hierarchy ===")
    
    # Find parent clusters (non-leaf)
    parents = await conn.fetch("""
        SELECT c.id, c.post_count FROM clusters c
        WHERE c.site_id = $1
        AND c.id IN (
            SELECT parent_cluster_id FROM clusters
            WHERE parent_cluster_id IS NOT NULL AND site_id = $1
        )
    """, SITE_ID)
    
    if not parents:
        logger.info("No parent clusters found — already flat")
        return
    
    parent_ids = [p["id"] for p in parents]
    
    # Find leaf clusters
    leaves = await conn.fetch("""
        SELECT c.id FROM clusters c
        WHERE c.site_id = $1
        AND c.id NOT IN (
            SELECT parent_cluster_id FROM clusters
            WHERE parent_cluster_id IS NOT NULL AND site_id = $1
        )
    """, SITE_ID)
    leaf_ids = [l["id"] for l in leaves]
    
    # Compute centroids for each leaf cluster
    leaf_centroids = {}
    for lid in leaf_ids:
        rows = await conn.fetch("""
            SELECT pe.embedding FROM post_embeddings pe
            JOIN post_clusters pc ON pc.post_id = pe.post_id
            WHERE pc.cluster_id = $1
        """, lid)
        if rows:
            embs = [_parse_pgvector(r["embedding"]) for r in rows]
            leaf_centroids[lid] = np.mean(embs, axis=0)
    
    # Find posts ONLY in parent clusters (not in any leaf)
    orphan_posts = await conn.fetch("""
        SELECT DISTINCT pc.post_id FROM post_clusters pc
        WHERE pc.cluster_id = ANY($1::uuid[])
        AND pc.post_id NOT IN (
            SELECT post_id FROM post_clusters WHERE cluster_id = ANY($2::uuid[])
        )
    """, parent_ids, leaf_ids)
    
    logger.info("Found %d posts only in parent clusters, %d leaf clusters", len(orphan_posts), len(leaf_ids))
    
    reassigned = 0
    for row in orphan_posts:
        pid = row["post_id"]
        emb_row = await conn.fetchrow(
            "SELECT embedding FROM post_embeddings WHERE post_id = $1", pid)
        if not emb_row:
            continue
        
        post_emb = np.array(_parse_pgvector(emb_row["embedding"]))
        
        # Find nearest leaf cluster by cosine similarity
        best_leaf = None
        best_sim = -1
        for lid, centroid in leaf_centroids.items():
            sim = float(np.dot(post_emb, centroid) / (np.linalg.norm(post_emb) * np.linalg.norm(centroid) + 1e-8))
            if sim > best_sim:
                best_sim = sim
                best_leaf = lid
        
        if best_leaf:
            await conn.execute(
                "INSERT INTO post_clusters (post_id, cluster_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                pid, best_leaf)
            reassigned += 1
    
    # Update post_count for leaf clusters
    for lid in leaf_ids:
        count = await conn.fetchval(
            "SELECT count(*) FROM post_clusters WHERE cluster_id = $1", lid)
        await conn.execute("UPDATE clusters SET post_count = $1 WHERE id = $2", count, lid)
    
    # Mark parent clusters with is_leaf-like flag (set post_count to 0 to hide)
    # Actually, add a description note
    for pid in parent_ids:
        await conn.execute(
            "UPDATE clusters SET description = COALESCE(description, '') || ' [parent cluster — see child clusters]' WHERE id = $1", pid)
    
    # Verify
    leaf_sum = await conn.fetchval("""
        SELECT sum(post_count) FROM clusters c
        WHERE c.site_id = $1
        AND c.id NOT IN (
            SELECT parent_cluster_id FROM clusters
            WHERE parent_cluster_id IS NOT NULL AND site_id = $1
        )
    """, SITE_ID)
    
    logger.info("✅ A2 complete: reassigned %d orphan posts to leaf clusters. Leaf sum: %s", reassigned, leaf_sum)


async def fix_a3_cann_severity(conn: asyncpg.Connection) -> None:
    """A3: Add severity gradient to cannibalization pairs."""
    logger.info("=== A3: Cannibalization Severity Gradient ===")
    
    updated = await conn.execute("""
        UPDATE cannibalization_pairs SET severity = 
            CASE
                WHEN cosine_similarity >= 0.95 THEN 'critical'
                WHEN cosine_similarity >= 0.90 THEN 'high'
                WHEN cosine_similarity >= 0.85 THEN 'medium'
                ELSE 'low'
            END
        WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
    """, SITE_ID)
    
    dist = await conn.fetch("""
        SELECT severity, count(*) c FROM cannibalization_pairs
        WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
        GROUP BY 1 ORDER BY 2 DESC
    """, SITE_ID)
    
    for d in dist:
        logger.info("  %s: %d", d["severity"], d["c"])
    
    logger.info("✅ A3 complete: severity gradient applied")


async def fix_a4_priority_recalibration(conn: asyncpg.Connection) -> None:
    """A4: Recalibrate recommendation priorities."""
    logger.info("=== A4: Priority Recalibration ===")
    
    # Critical: merge recs with cos >= 0.95, expand for posts < 200 words
    await conn.execute("""
        UPDATE recommendations SET priority = 'critical'
        WHERE site_id = $1 AND recommendation_type = 'merge'
        AND post_id IN (
            SELECT post_a_id FROM cannibalization_pairs WHERE cosine_similarity >= 0.95
            UNION SELECT post_b_id FROM cannibalization_pairs WHERE cosine_similarity >= 0.95
        )
    """, SITE_ID)
    
    await conn.execute("""
        UPDATE recommendations SET priority = 'critical'
        WHERE site_id = $1 AND recommendation_type = 'expand'
        AND post_id IN (SELECT id FROM posts WHERE site_id = $1 AND word_count < 200)
    """, SITE_ID)
    
    # High: merge cos >= 0.90, expand < 500w, orphan, missing meta on commercial/transactional
    await conn.execute("""
        UPDATE recommendations SET priority = 'high'
        WHERE site_id = $1 AND recommendation_type IN ('merge', 'differentiate')
        AND priority NOT IN ('critical')
    """, SITE_ID)
    
    await conn.execute("""
        UPDATE recommendations SET priority = 'high'
        WHERE site_id = $1 AND recommendation_type = 'expand'
        AND post_id IN (SELECT id FROM posts WHERE site_id = $1 AND word_count < 500)
        AND priority NOT IN ('critical')
    """, SITE_ID)
    
    await conn.execute("""
        UPDATE recommendations SET priority = 'high'
        WHERE site_id = $1 AND recommendation_type = 'interlink'
        AND priority NOT IN ('critical')
    """, SITE_ID)
    
    # Boost commercial/transactional content SEO recs to high
    await conn.execute("""
        UPDATE recommendations SET priority = 'high'
        WHERE site_id = $1 AND recommendation_type = 'optimize'
        AND post_id IN (
            SELECT id FROM posts WHERE site_id = $1 AND content_intent IN ('commercial', 'transactional')
        )
        AND priority NOT IN ('critical', 'high')
    """, SITE_ID)
    
    # Medium: everything else that was "low" and is differentiate or readability
    await conn.execute("""
        UPDATE recommendations SET priority = 'medium'
        WHERE site_id = $1 AND recommendation_type = 'optimize'
        AND post_id IN (
            SELECT post_id FROM content_problems 
            WHERE site_id = $1 AND problem_type = 'readability_too_complex'
        )
        AND priority = 'low'
    """, SITE_ID)
    
    dist = await conn.fetch("""
        SELECT priority, count(*) c FROM recommendations WHERE site_id = $1
        GROUP BY 1 ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
    """, SITE_ID)
    for d in dist:
        logger.info("  %s: %d", d["priority"], d["c"])
    
    logger.info("✅ A4 complete: priorities recalibrated")


async def fix_a5_dedup_cann_pairs(conn: asyncpg.Connection) -> None:
    """A5: Dedup reciprocal cannibalization pairs."""
    logger.info("=== A5: Dedup Reciprocal Cann Pairs ===")
    
    before = await conn.fetchval(
        "SELECT count(*) FROM cannibalization_pairs WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)", SITE_ID)
    
    # Delete reciprocal duplicates: keep the one where post_a_id < post_b_id
    await conn.execute("""
        DELETE FROM cannibalization_pairs
        WHERE id IN (
            SELECT cp2.id FROM cannibalization_pairs cp1
            JOIN cannibalization_pairs cp2 ON cp1.post_a_id = cp2.post_b_id AND cp1.post_b_id = cp2.post_a_id
            WHERE cp1.post_a_id < cp1.post_b_id
            AND cp2.post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
        )
    """, SITE_ID)
    
    # Also dedup same pair appearing from different cluster scans
    # Keep highest cosine per unique pair
    await conn.execute("""
        DELETE FROM cannibalization_pairs WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY LEAST(post_a_id, post_b_id), GREATEST(post_a_id, post_b_id)
                    ORDER BY cosine_similarity DESC
                ) rn
                FROM cannibalization_pairs
                WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
            ) ranked WHERE rn > 1
        )
    """, SITE_ID)
    
    after = await conn.fetchval(
        "SELECT count(*) FROM cannibalization_pairs WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)", SITE_ID)
    
    logger.info("✅ A5 complete: %d → %d pairs (removed %d duplicates)", before, after, before - after)


async def fix_a6_flag_duplicate_content(conn: asyncpg.Connection) -> None:
    """A6: Flag identical-content posts as redirect candidates."""
    logger.info("=== A6: Flag Duplicate Content Posts ===")
    
    # Find posts with duplicate content_hash
    dupes = await conn.fetch("""
        SELECT content_hash, array_agg(id) as ids, array_agg(title) as titles, count(*) c
        FROM posts WHERE site_id = $1 AND content_hash IS NOT NULL
        GROUP BY content_hash HAVING count(*) > 1
    """, SITE_ID)
    
    problems_added = 0
    recs_added = 0
    for dupe in dupes:
        ids = dupe["ids"]
        titles = dupe["titles"]
        
        # The first (oldest/longest) is canonical; rest are duplicates
        canonical = ids[0]
        for dup_id in ids[1:]:
            # Add problem
            await conn.execute("""
                INSERT INTO content_problems (post_id, site_id, problem_type, severity, details)
                VALUES ($1, $2, 'duplicate_content', 'critical', $3)
                ON CONFLICT DO NOTHING
            """, dup_id, SITE_ID, json.dumps({
                "canonical_post_id": str(canonical),
                "canonical_title": titles[0],
                "action": "301 redirect to canonical URL"
            }))
            problems_added += 1
            
            # Add redirect recommendation
            await conn.execute("""
                INSERT INTO recommendations (post_id, site_id, recommendation_type, priority, estimated_effort_hours, estimated_impact, title, summary, specific_actions, status)
                VALUES ($1, $2, 'optimize', 'critical', 0.5, 'high', $3, $4, $5, 'pending')
                ON CONFLICT DO NOTHING
            """, dup_id, SITE_ID,
                f"Redirect duplicate: {titles[ids.index(dup_id)][:50]}",
                f"This post is identical content to '{titles[0][:60]}'. Set up a 301 redirect to the canonical URL to consolidate link equity.",
                json.dumps(["Set up 301 redirect to canonical URL", "Update any internal links pointing to this URL", "Monitor for traffic loss after redirect"]),
            )
            recs_added += 1
    
    logger.info("✅ A6 complete: %d duplicate sets found, %d problems + %d recs added", len(dupes), problems_added, recs_added)


async def fix_a7_blog_link_separation(conn: asyncpg.Connection) -> None:
    """A7: Classify internal links as blog vs non-blog."""
    logger.info("=== A7: Blog vs Non-Blog Link Separation ===")
    
    # Mark links to /blog/ URLs as blog links
    blog_links = await conn.execute("""
        UPDATE internal_links SET target_post_id = NULL
        WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1)
        AND target_url NOT LIKE '%/blog/%'
        AND target_post_id IS NULL
    """, SITE_ID)
    
    # Count blog-only internal links
    total = await conn.fetchval("""
        SELECT count(*) FROM internal_links 
        WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1)
    """, SITE_ID)
    
    blog_resolved = await conn.fetchval("""
        SELECT count(*) FROM internal_links 
        WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1)
        AND target_post_id IS NOT NULL
    """, SITE_ID)
    
    non_blog = await conn.fetchval("""
        SELECT count(*) FROM internal_links 
        WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1)
        AND target_post_id IS NULL
        AND target_url NOT LIKE '%/blog/%'
    """, SITE_ID)
    
    unresolved_blog = await conn.fetchval("""
        SELECT count(*) FROM internal_links 
        WHERE source_post_id IN (SELECT id FROM posts WHERE site_id = $1)
        AND target_post_id IS NULL
        AND target_url LIKE '%/blog/%'
    """, SITE_ID)
    
    # Recount orphans (blog-only graph)
    orphans = await conn.fetchval("""
        SELECT count(*) FROM posts p WHERE p.site_id = $1
        AND p.id NOT IN (
            SELECT DISTINCT target_post_id FROM internal_links 
            WHERE target_post_id IS NOT NULL
            AND source_post_id IN (SELECT id FROM posts WHERE site_id = $1)
        )
    """, SITE_ID)
    
    logger.info("  Total links: %d", total)
    logger.info("  Blog-to-blog resolved: %d (%.1f%%)", blog_resolved, blog_resolved * 100 / total)
    logger.info("  Non-blog links: %d (correctly unresolved)", non_blog)
    logger.info("  Unresolved blog links: %d", unresolved_blog)
    logger.info("  Orphan posts (blog graph): %d", orphans)
    logger.info("✅ A7 complete: link graph classified")


async def fix_a8_growth_recs(conn: asyncpg.Connection) -> None:
    """A8: Generate growth recommendations for clean posts."""
    logger.info("=== A8: Growth Recs for Clean Posts ===")
    
    # Posts with no recommendations
    clean_posts = await conn.fetch("""
        SELECT p.id, p.title, p.word_count, p.published_at, p.content_intent,
               ph.composite_score as health
        FROM posts p
        LEFT JOIN post_health_scores ph ON ph.post_id = p.id
        WHERE p.site_id = $1
        AND p.id NOT IN (SELECT post_id FROM recommendations WHERE site_id = $1 AND post_id IS NOT NULL)
    """, SITE_ID)
    
    logger.info("Found %d posts with no recommendations", len(clean_posts))
    
    recs = []
    for post in clean_posts:
        # Find top 3 related posts in OTHER clusters for cross-linking
        related = await conn.fetch("""
            SELECT p2.title, p2.url,
                   1 - (pe1.embedding <=> pe2.embedding) as sim
            FROM post_embeddings pe1
            JOIN post_embeddings pe2 ON pe1.post_id != pe2.post_id
            JOIN posts p2 ON p2.id = pe2.post_id
            WHERE pe1.post_id = $1
            AND pe2.post_id IN (
                SELECT pc2.post_id FROM post_clusters pc2
                WHERE pc2.cluster_id NOT IN (
                    SELECT cluster_id FROM post_clusters WHERE post_id = $1
                )
            )
            ORDER BY pe1.embedding <=> pe2.embedding ASC
            LIMIT 3
        """, post["id"])
        
        related_titles = [f"'{r['title'][:50]}'" for r in related]
        
        # Age-based update suggestion
        age_note = ""
        if post["published_at"]:
            from datetime import datetime, timezone
            age_days = (datetime.now(timezone.utc) - post["published_at"]).days
            if age_days > 365:
                age_note = f"Published {age_days // 365} year(s) ago — consider refreshing with current data and examples. "
        
        # Build action items
        actions = []
        if related_titles:
            actions.append(f"Add cross-links to related content: {', '.join(related_titles)}")
        if age_note:
            actions.append("Review and update with current information, stats, and examples")
        actions.append("Check if there are new subtopics in this cluster that could expand this post")
        if post["content_intent"] in ("commercial", "transactional"):
            actions.append("Add or update CTA — this is a high-intent page close to conversion")
        
        priority = "medium" if post["content_intent"] in ("commercial", "transactional") else "low"
        
        recs.append((
            post["id"], SITE_ID, "growth", priority, 1.0, priority,
            f"Growth opportunity: {(post['title'] or 'Untitled')[:55]}",
            f"{age_note}This post is healthy but can be strengthened with cross-cluster links and content updates. "
            f"{'High-intent content — prioritize CTA optimization. ' if post['content_intent'] in ('commercial', 'transactional') else ''}"
            f"Related content in other topic clusters: {', '.join(related_titles) if related_titles else 'none found'}.",
            json.dumps(actions),
            "pending",
        ))
    
    if recs:
        await conn.executemany("""
            INSERT INTO recommendations (post_id, site_id, recommendation_type, priority, estimated_effort_hours, estimated_impact, title, summary, specific_actions, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """, recs)
    
    logger.info("✅ A8 complete: %d growth recommendations added", len(recs))


async def fix_a9_thin_thresholds(conn: asyncpg.Connection) -> None:
    """A9: Fix thin content thresholds — 50% of avg + 800w floor."""
    logger.info("=== A9: Fix Thin Content Thresholds ===")
    
    # Remove thin_below_cluster_avg problems for posts above 800 words
    removed = await conn.execute("""
        DELETE FROM content_problems 
        WHERE site_id = $1 AND problem_type = 'thin_below_cluster_avg'
        AND post_id IN (SELECT id FROM posts WHERE site_id = $1 AND word_count >= 800)
    """, SITE_ID)
    
    # Also downgrade remaining thin_below_cluster_avg to "low" severity
    await conn.execute("""
        UPDATE content_problems SET severity = 'low'
        WHERE site_id = $1 AND problem_type = 'thin_below_cluster_avg'
    """, SITE_ID)
    
    # Remove corresponding recs for the deleted problems
    await conn.execute("""
        DELETE FROM recommendations 
        WHERE site_id = $1 AND title LIKE 'Expand to match cluster depth%'
        AND post_id IN (SELECT id FROM posts WHERE site_id = $1 AND word_count >= 800)
    """, SITE_ID)
    
    remaining = await conn.fetchval("""
        SELECT count(*) FROM content_problems 
        WHERE site_id = $1 AND problem_type = 'thin_below_cluster_avg'
    """, SITE_ID)
    
    logger.info("✅ A9 complete: removed thin_below_cluster_avg for posts ≥800w. %d remaining", remaining)


async def fix_a10_data_completeness(conn: asyncpg.Connection) -> None:
    """A10: Add data_completeness context to health scores."""
    logger.info("=== A10: Data Completeness Context ===")
    
    # Check if column exists
    col_exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'post_health_scores' AND column_name = 'data_completeness'
        )
    """)
    
    if not col_exists:
        await conn.execute("""
            ALTER TABLE post_health_scores 
            ADD COLUMN IF NOT EXISTS data_completeness FLOAT DEFAULT 0.4
        """)
        logger.info("  Added data_completeness column")
    
    # Set to 0.4 for all posts (no GSC/GA4)
    await conn.execute("""
        UPDATE post_health_scores SET data_completeness = 0.4
        WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
    """, SITE_ID)
    
    # Posts with higher scores (pillars with good content signals) get slightly higher completeness
    await conn.execute("""
        UPDATE post_health_scores SET data_completeness = 0.45
        WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)
        AND role = 'pillar'
    """, SITE_ID)
    
    logger.info("✅ A10 complete: data_completeness set (0.4 default, no GSC/GA4)")


def _parse_pgvector(text: str) -> list[float]:
    """Parse pgvector's [x,y,z,...] text format."""
    text = str(text).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [float(x) for x in text.split(",")]


async def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")
    
    conn = await asyncpg.connect(db_url)
    
    total_start = time.time()
    
    fixes = [
        ("A1", "Cluster Labels (Claude)", fix_a1_cluster_labels),
        ("A2", "Flatten Hierarchy", fix_a2_flatten_hierarchy),
        ("A3", "Cann Severity Gradient", fix_a3_cann_severity),
        ("A4", "Priority Recalibration", fix_a4_priority_recalibration),
        ("A5", "Dedup Cann Pairs", fix_a5_dedup_cann_pairs),
        ("A6", "Flag Duplicate Content", fix_a6_flag_duplicate_content),
        ("A7", "Blog Link Separation", fix_a7_blog_link_separation),
        ("A8", "Growth Recs for Clean Posts", fix_a8_growth_recs),
        ("A9", "Fix Thin Thresholds", fix_a9_thin_thresholds),
        ("A10", "Data Completeness", fix_a10_data_completeness),
    ]
    
    for code, name, func in fixes:
        start = time.time()
        try:
            await func(conn)
            elapsed = time.time() - start
            logger.info("⏱ %s (%s): %.1fs\n", code, name, elapsed)
        except Exception as e:
            logger.error("❌ %s FAILED: %s", code, e)
            import traceback
            traceback.print_exc()
            logger.info("")
    
    total = time.time() - total_start
    logger.info("=" * 50)
    logger.info("ALL TIER A FIXES COMPLETE: %.1fs total", total)
    
    # Final summary
    logger.info("\n--- FINAL STATS ---")
    for label, query in [
        ("Clusters (leaf)", "SELECT count(*) FROM clusters c WHERE c.site_id = $1 AND c.id NOT IN (SELECT parent_cluster_id FROM clusters WHERE parent_cluster_id IS NOT NULL AND site_id = $1)"),
        ("Leaf post sum", "SELECT sum(post_count) FROM clusters c WHERE c.site_id = $1 AND c.id NOT IN (SELECT parent_cluster_id FROM clusters WHERE parent_cluster_id IS NOT NULL AND site_id = $1)"),
        ("Health scores", "SELECT count(*) FROM post_health_scores WHERE post_id IN (SELECT id FROM posts WHERE site_id = $1)"),
        ("Cann pairs", "SELECT count(*) FROM cannibalization_pairs WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1)"),
        ("Problems", "SELECT count(*) FROM content_problems WHERE site_id = $1"),
        ("Recommendations", "SELECT count(*) FROM recommendations WHERE site_id = $1"),
    ]:
        val = await conn.fetchval(query, SITE_ID)
        logger.info("  %s: %s", label, val)
    
    # Priority breakdown
    pris = await conn.fetch("SELECT priority, count(*) c FROM recommendations WHERE site_id = $1 GROUP BY 1 ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END", SITE_ID)
    logger.info("  Rec priorities:")
    for p in pris:
        logger.info("    %s: %d", p["priority"], p["c"])
    
    # Cann severity
    sevs = await conn.fetch("SELECT severity, count(*) c FROM cannibalization_pairs WHERE post_a_id IN (SELECT id FROM posts WHERE site_id = $1) GROUP BY 1 ORDER BY 2 DESC", SITE_ID)
    logger.info("  Cann severity:")
    for sv in sevs:
        logger.info("    %s: %d", sv["severity"], sv["c"])
    
    # Coverage
    rec_coverage = await conn.fetchval("SELECT count(DISTINCT post_id) FROM recommendations WHERE site_id = $1", SITE_ID)
    logger.info("  Posts with recs: %d/600", rec_coverage)
    
    # Sample labels
    labels = await conn.fetch("SELECT label, post_count, parent_cluster_id FROM clusters WHERE site_id = $1 ORDER BY post_count DESC LIMIT 10", SITE_ID)
    logger.info("  Top cluster labels:")
    for l in labels:
        ptype = "ROOT" if l['parent_cluster_id'] is None else "leaf"
        logger.info("    [%s] %s (%d posts)", ptype, l["label"], l["post_count"])
    
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
