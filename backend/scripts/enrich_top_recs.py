"""AI-enrich top 50 recommendations with Claude for specific, actionable guidance.

Reads the top 50 highest-priority recommendations, fetches the relevant post content,
and uses Claude to generate specific merge plans, paragraph-level guidance, and
estimated impact.

Cost: ~$1-2 (50 calls, ~1K input + 500 output tokens each)
"""
import asyncio, asyncpg, json, logging, os, sys, time
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

SITE_ID = UUID("32296e5d-7924-4d9f-92b8-7f774c634fad")


async def main():
    from dotenv import load_dotenv
    load_dotenv()
    
    import anthropic
    
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    
    # Get top 50 recs by priority score
    recs = await conn.fetch("""
        SELECT r.id, r.post_id, r.recommendation_type, r.title, r.summary,
               r.specific_actions, r.priority,
               p.title AS post_title, p.url, p.word_count,
               LEFT(p.body_text, 2000) AS body_excerpt
        FROM recommendations r
        JOIN posts p ON p.id = r.post_id
        WHERE r.site_id = $1
        AND r.specific_actions::text NOT LIKE '%ai_enriched%'
        ORDER BY r.priority DESC
        LIMIT 50
    """, SITE_ID)
    
    log.info("Enriching %d top recommendations", len(recs))
    stats = {"enriched": 0, "errors": 0}
    t0 = time.time()
    
    for i, rec in enumerate(recs):
        try:
            # Build context based on rec type
            rec_type = rec["recommendation_type"]
            context = f"Post: {rec['post_title']}\nURL: {rec['url']}\nWord count: {rec['word_count']}\nCurrent recommendation: {rec['title']}\n{rec['summary'] or ''}"
            
            # For merge/differentiate, get the other post
            if rec_type in ("merge", "differentiate", "redirect"):
                # Try to find the paired post from cannibalization
                pair = await conn.fetchrow("""
                    SELECT p.title, p.url, p.word_count, LEFT(p.body_text, 1500) AS body_excerpt
                    FROM cannibalization_pairs cp
                    JOIN posts p ON p.id = CASE 
                        WHEN cp.post_a_id = $1 THEN cp.post_b_id 
                        ELSE cp.post_a_id END
                    WHERE (cp.post_a_id = $1 OR cp.post_b_id = $1)
                    ORDER BY cp.cosine_similarity DESC
                    LIMIT 1
                """, rec["post_id"])
                
                if pair:
                    context += f"\n\nOverlapping post: {pair['title']}\nURL: {pair['url']}\nWord count: {pair['word_count']}"
                    context += f"\n\nPost A excerpt:\n{rec['body_excerpt'][:1000]}"
                    context += f"\n\nPost B excerpt:\n{pair['body_excerpt'][:1000]}"
            else:
                context += f"\n\nContent excerpt:\n{rec['body_excerpt'][:1500]}"
            
            # Customize prompt by rec type
            if rec_type in ("merge", "redirect"):
                prompt = f"""You are a content strategist. Based on these two overlapping blog posts, provide a specific merge plan.

{context}

Respond with ONLY a JSON object (no markdown):
{{"merge_plan": "Which post to keep as primary and why (1 sentence)",
"keep_url": "URL of the post to keep",
"redirect_url": "URL to 301 redirect",
"sections_to_merge": ["Specific sections/paragraphs from the secondary post to incorporate into the primary"],
"estimated_word_count": "Target word count for merged post",
"estimated_impact": "Expected SEO impact (e.g., 'Consolidates ranking signals, likely 10-20% organic traffic increase for target keywords')"}}"""
            
            elif rec_type == "differentiate":
                prompt = f"""You are a content strategist. These two posts overlap significantly. Provide a specific differentiation plan.

{context}

Respond with ONLY a JSON object (no markdown):
{{"differentiation_plan": "How to make these posts distinct (1-2 sentences)",
"post_a_angle": "Specific angle/focus for post A",
"post_b_angle": "Specific angle/focus for post B", 
"keywords_post_a": ["3-5 specific target keywords for post A"],
"keywords_post_b": ["3-5 specific target keywords for post B"],
"sections_to_rewrite": ["Specific overlapping sections that need rewriting"],
"estimated_impact": "Expected SEO impact"}}"""
            
            elif rec_type == "expand":
                prompt = f"""You are a content strategist. This thin blog post needs to be expanded. Provide specific guidance.

{context}

Respond with ONLY a JSON object (no markdown):
{{"expansion_plan": "What this post needs (1-2 sentences)",
"sections_to_add": ["3-5 specific new sections with suggested H2 headings"],
"target_word_count": "Recommended final word count",
"content_gaps": ["Specific topics/questions the current post doesn't address but should"],
"estimated_impact": "Expected SEO impact"}}"""
            
            elif rec_type == "optimize":
                prompt = f"""You are an SEO content strategist. This blog post needs optimization. Provide specific, actionable guidance.

{context}

Respond with ONLY a JSON object (no markdown):
{{"optimization_plan": "What needs to change (1-2 sentences)",
"title_suggestion": "Improved title if current one is suboptimal, or 'Current title is good'",
"meta_description": "Suggested meta description (150-160 chars)",
"internal_links_to_add": ["2-3 specific blog posts this should link to, based on the content topic"],
"content_improvements": ["2-3 specific paragraphs or sections to improve and how"],
"estimated_impact": "Expected SEO impact"}}"""
            
            elif rec_type == "interlink":
                prompt = f"""You are a content strategist. This blog post is an orphan with no inbound internal links. Suggest specific interlinking.

{context}

Respond with ONLY a JSON object (no markdown):
{{"interlink_plan": "Why this post deserves more internal links (1 sentence)",
"suggested_anchor_texts": ["3-5 natural anchor text phrases that could link to this post"],
"likely_linking_posts": ["3-5 types of blog posts (by topic) that should link here"],
"placement_tips": "Where in linking posts the link should be placed (e.g., 'in the introduction when mentioning X' or 'as a related resource at the end')",
"estimated_impact": "Expected impact on crawl depth and rankings"}}"""
            
            else:
                # Generic enrichment
                prompt = f"""You are a content strategist. Provide specific, actionable guidance for this recommendation.

{context}

Respond with ONLY a JSON object (no markdown):
{{"action_plan": "Specific steps to implement this recommendation",
"priority_rationale": "Why this matters",
"estimated_impact": "Expected SEO impact",
"time_estimate": "Estimated time to implement"}}"""
            
            # Call Claude
            message = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            
            response_text = message.content[0].text.strip()
            
            # Parse JSON response
            try:
                # Handle potential markdown wrapping
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                enrichment = json.loads(response_text)
            except json.JSONDecodeError:
                enrichment = {"raw_response": response_text}
            
            # Update the recommendation with enriched data
            current_actions = rec["specific_actions"]
            if isinstance(current_actions, str):
                try:
                    current_actions = json.loads(current_actions)
                except:
                    current_actions = [current_actions] if current_actions else []
            elif current_actions is None:
                current_actions = []
            
            # Merge enrichment into specific_actions
            enriched_actions = {
                "ai_enriched": True,
                "ai_guidance": enrichment,
                "original_actions": current_actions,
            }
            
            await conn.execute("""
                UPDATE recommendations SET
                    specific_actions = $1,
                    updated_at = NOW()
                WHERE id = $2
            """, json.dumps(enriched_actions), rec["id"])
            
            stats["enriched"] += 1
            
            if (i+1) % 10 == 0:
                elapsed = time.time() - t0
                log.info("[%d/50] enriched=%d err=%d (%.1fs)", i+1, stats["enriched"], stats["errors"], elapsed)
            
            # Rate limit — max 3/sec
            await asyncio.sleep(0.4)
            
        except Exception as e:
            log.error("[%d] Error enriching rec %s: %s", i+1, rec["id"], str(e)[:100])
            stats["errors"] += 1
    
    elapsed = time.time() - t0
    log.info("DONE in %.0fs. enriched=%d errors=%d", elapsed, stats["enriched"], stats["errors"])
    
    # Verify
    enriched_count = await conn.fetchval("""
        SELECT count(*) FROM recommendations 
        WHERE site_id=$1 AND specific_actions::text LIKE '%ai_enriched%'
    """, SITE_ID)
    log.info("Total AI-enriched recs in DB: %d", enriched_count)
    
    await conn.close()

asyncio.run(main())
