"""Tier 1 fast template-based recommendations — zero Claude API calls.

Generates actionable recommendations from detected problems, cannibalization
pairs, and link suggestions using deterministic templates. Covers ~90% of
recommendation patterns without any LLM calls.

For deep AI-powered recommendations (rewrites, strategic analysis), see
the Tier 2 enrichment in recommendations.py.
"""

import logging
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


# ── Templates by problem type ──

_TEMPLATES: dict[str, dict[str, Any]] = {
    "thin_content": {
        "recommendation_type": "expand",
        "title_tpl": "Expand thin content: {title}",
        "summary_tpl": "This post has {word_count} words, which is below the {threshold}-word threshold for {content_type} content. Expand to at least {target_words} words to match cluster average.",
        "actions_tpl": [
            "Add {words_needed}+ words of substantive content",
            "Research what top-ranking competitors cover that this post doesn't",
            "Add practical examples, case studies, or data points",
            "Consider adding an FAQ section addressing related questions",
        ],
        "effort_hours": 2.0,
        "priority_fn": lambda d: "high" if d.get("word_count", 0) < 300 else "medium",
    },
    "thin_below_cluster_avg": {
        "recommendation_type": "expand",
        "title_tpl": "Expand to match cluster depth: {title}",
        "summary_tpl": "At {word_count} words, this post is significantly below the cluster average of {cluster_avg} words. Posts below cluster average tend to underperform in rankings.",
        "actions_tpl": [
            "Expand by {words_needed}+ words to reach cluster average ({cluster_avg} words)",
            "Study the top 3 posts in this cluster for section ideas",
            "Add depth on subtopics your competitors cover",
        ],
        "effort_hours": 1.5,
        "priority_fn": lambda d: "medium" if d.get("word_count", 0) > 500 else "high",
    },
    "seo_title_length": {
        "recommendation_type": "optimize",
        "title_tpl": "Fix title length: {title}",
        "summary_fn": lambda d: (
            f"Title is only {d['title_length']} characters (recommended: 30-60). "
            "Short titles miss keyword opportunities and look sparse in search results."
            if d.get("title_length", 50) < 30
            else f"Title is {d['title_length']} characters (recommended: 30-60). "
            "Titles over 60 characters get truncated in Google search results, reducing click-through rate."
        ),
        "actions_fn": lambda d: (
            [
                f"Expand title from {d['title_length']} to 30-60 characters",
                "Add the primary keyword and a descriptive modifier (e.g., 'Easy', 'Homemade', 'Best')",
                "Include the content type (Recipe, Guide, How-To) if not already present",
            ]
            if d.get("title_length", 50) < 30
            else [
                f"Shorten title from {d['title_length']} to under 60 characters",
                "Front-load the primary keyword in the first 40 characters",
                "Remove filler words (ultimate, comprehensive, complete guide to) unless they add value",
            ]
        ),
        "effort_hours": 0.25,
        "priority_fn": lambda d: "low",
    },
    "seo_missing_meta": {
        "recommendation_type": "optimize",
        "title_tpl": "Add meta description: {title}",
        "summary_tpl": "This post has no meta description. Google will auto-generate one from page content, which is often suboptimal for click-through rate.",
        "actions_tpl": [
            "Write a 150-160 character meta description",
            "Include the primary keyword naturally",
            "Add a compelling reason to click (number, benefit, or question)",
            "Match search intent — if informational, promise the answer; if commercial, highlight the comparison",
        ],
        "effort_hours": 0.25,
        "priority_fn": lambda d: "medium",
    },
    "seo_no_images": {
        "recommendation_type": "optimize",
        "title_tpl": "Add visual content: {title}",
        "summary_tpl": "No images detected in this post. Posts with relevant images get 94% more views than text-only content.",
        "actions_tpl": [
            "Add at least 1 relevant image per 300 words of content",
            "Include descriptive alt text with target keywords",
            "Consider adding a hero image, diagrams, or screenshots",
            "Use WebP format for faster loading",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "low",
    },
    "readability_too_complex": {
        "recommendation_type": "optimize",
        "title_tpl": "Improve readability: {title}",
        "summary_tpl": "Flesch readability score of {readability_score:.0f} is below the industry threshold of {threshold}. Complex writing reduces engagement and time on page.",
        "actions_tpl": [
            "Break long sentences (>25 words) into shorter ones",
            "Replace jargon with simpler alternatives where possible",
            "Add subheadings every 2-3 paragraphs to improve scannability",
            "Use bullet points for lists of 3+ items",
        ],
        "effort_hours": 1.0,
        "priority_fn": lambda d: "medium",
    },
    "orphan": {
        "recommendation_type": "interlink",
        "title_tpl": "Fix orphan page: {title}",
        "summary_tpl": "This post has no internal links pointing to it. Orphan pages are nearly invisible to search engines and get minimal crawl budget.",
        "actions_tpl": [
            "Add links to this post from at least 3 related posts",
            "Link from your highest-traffic posts in the same cluster",
            "Use descriptive anchor text (not 'click here')",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "high",
    },
    # ── Content decay with AI citation framing (GEO-6) ────────────────────────
    "decay_severe": {
        "recommendation_type": "update",
        "title_tpl": "Urgent: update decaying content: {title}",
        "summary_tpl": (
            "This post hasn't been updated in over 12 months and is losing rankings. "
            "In 2026, stale content faces a double penalty: Google ranks it lower AND AI systems "
            "stop citing it entirely. Posts older than 12 months are rarely cited by ChatGPT or Perplexity."
        ),
        "actions_tpl": [
            "Update all statistics, data points, and examples to current year",
            "Add a visible 'Last updated: [today's date]' timestamp",
            "Refresh the introduction with current context and a TL;DR answer",
            "Add an FAQ section with 3-5 current questions on this topic",
            "Update the dateModified in your Article JSON-LD schema",
            "Review and update any broken or outdated external links",
        ],
        "effort_hours": 2.0,
        "priority_fn": lambda d: "high",
    },
    "decay_moderate": {
        "recommendation_type": "update",
        "title_tpl": "Refresh stale content: {title}",
        "summary_tpl": (
            "This post hasn't been updated in 6-12 months. AI citation risk: "
            "AI systems actively replace older sources with fresher competitors. "
            "Without an update, this content is becoming invisible to AI-generated answers."
        ),
        "actions_tpl": [
            "Update the 'Last updated' date after making substantive edits",
            "Refresh any statistics or data points older than 6 months",
            "Add 1-2 new insights, examples, or data points",
            "Check that the opening still directly answers the primary query",
        ],
        "effort_hours": 1.0,
        "priority_fn": lambda d: "medium",
    },
    # ── 2026 AI-era SEO templates ─────────────────────────────────────────────
    "low_ai_citability": {
        "recommendation_type": "improve_ai_citability",
        "title_tpl": "Improve AI citability: {title}",
        "summary_tpl": (
            "AI Citability Score: {citability_score}/100. "
            "This post lacks the signals AI systems use when selecting content to cite or quote. "
            "AI-cited content gets traffic even when traditional clicks decline."
        ),
        "actions_tpl": [
            "Add at least one data table comparing options, benchmarks, or statistics",
            "Include first-person experience language: 'In our testing...', 'When we implemented...'",
            "Add 2-3 original statistics with specific numbers (not just citing others)",
            "Start key H2 sections with a definition paragraph (40-80 words: '[Topic] is...')",
            "Include a numbered step sequence (ordered list with 4+ steps)",
        ],
        "effort_hours": 2.0,
        "priority_fn": lambda d: "high" if d.get("citability_score", 50) < 20 else "medium",
    },
    "weak_eeat": {
        "recommendation_type": "strengthen_eeat",
        "title_tpl": "Strengthen E-E-A-T signals: {title}",
        "summary_tpl": (
            "Weak E-E-A-T signals (score: {eeat_score}/100). "
            "96% of AI Overview citations come from high E-E-A-T content. "
            "Trust signals — author credentials, dates, citations — are now ranking factors."
        ),
        "actions_tpl": [
            "Add a visible author byline with the author's name",
            "Create an author bio section with credentials, title, and experience",
            "Add Author schema markup (JSON-LD with @type: Person, name, jobTitle, url)",
            "Display a visible publish/last-updated date using a <time> element",
            "Add 2-3 links to credible external sources (.gov, .edu, peer-reviewed journals)",
        ],
        "effort_hours": 1.0,
        "priority_fn": lambda d: "high" if d.get("eeat_score", 50) < 20 else "medium",
    },
    "missing_schema": {
        "recommendation_type": "add_schema",
        "title_tpl": "Add JSON-LD schema markup: {title}",
        "summary_tpl": (
            "No structured data detected on this page. "
            "Pages with Article or FAQ schema are significantly more likely to appear in AI Overviews "
            "and rich results. This is one of the highest-ROI technical SEO fixes available."
        ),
        "actions_tpl": [
            "Add Article JSON-LD with: @type, headline, datePublished, dateModified, author (@type: Person, name), image",
            "If post has Q&A content: add FAQPage schema with Question + Answer pairs",
            "If post is a tutorial: add HowTo schema with Step objects",
            "Validate schema at schema.org/validator after adding",
            "Add Organization schema to your site's homepage if not already present",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "high",
    },
    "poor_ai_structure": {
        "recommendation_type": "improve_ai_structure",
        "title_tpl": "Restructure for AI extraction: {title}",
        "summary_tpl": (
            "AI Extraction Score: {extraction_score}/100. "
            "This post doesn't answer its primary query in the first 200 words, "
            "and H2 sections don't lead with direct answers. "
            "AI systems prefer content that front-loads answers and uses clear structure."
        ),
        "actions_tpl": [
            "Move the core answer to the first 200 words — state what the post covers immediately",
            "Rewrite each H2 section to start with a 1-2 sentence direct answer before elaborating",
            "Add a concise TL;DR or key takeaways section at the top",
            "Convert any long prose answers to numbered lists or bullet points",
            "Add an FAQ section at the bottom addressing 3-5 common questions on this topic",
        ],
        "effort_hours": 1.5,
        "priority_fn": lambda d: "medium",
    },
    # ── GEO-specific problem types (GEO-3 / GEO-8) ──────────────────────────
    "geo_no_faq_section": {
        "recommendation_type": "add_faq_section",
        "title_tpl": "Add FAQ section for AI citation: {title}",
        "summary_tpl": (
            "This post has no FAQ section. Posts with structured FAQ sections are "
            "significantly more likely to be cited by ChatGPT, Perplexity, and Google AI Overviews. "
            "AI systems extract Q&A pairs directly from FAQ sections."
        ),
        "actions_tpl": [
            "Add an H2 'Frequently Asked Questions' section at the bottom of the post",
            "Include 3-5 questions phrased as users would prompt an AI (e.g. 'What is...', 'How do I...')",
            "Keep each answer concise: 40-100 words, directly answering the question",
            "Add FAQPage JSON-LD schema markup to match the FAQ section",
            "Use your top GSC queries for this topic as the FAQ questions",
        ],
        "effort_hours": 1.0,
        "priority_fn": lambda d: "medium",
    },
    "geo_no_question_headers": {
        "recommendation_type": "reformat_headers_geo",
        "title_tpl": "Reformat headers as questions for AI: {title}",
        "summary_tpl": (
            "Only {question_header_ratio:.0%} of H2/H3 headers are question-format. "
            "AI systems match natural language prompts to question-format headers. "
            "Target: at least 30% of headers should be questions."
        ),
        "actions_tpl": [
            "Reformat H2 headers as questions that match how users prompt AI",
            "Example: change 'Benefits of X' to 'What are the benefits of X?'",
            "Example: change 'Implementation Guide' to 'How do you implement X?'",
            "Keep some non-question headers for variety — target 30-50% questions",
            "Each question header should be followed by a direct 1-2 sentence answer",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "medium",
    },
    "geo_low_data_density": {
        "recommendation_type": "increase_data_density",
        "title_tpl": "Add data points for AI citation: {title}",
        "summary_tpl": (
            "Data density: {data_density_per_200w:.1f} data points per 200 words (target: 1.0). "
            "AI systems preferentially cite content with specific statistics, percentages, and measurements. "
            "Posts with higher data density are cited 2-3x more often."
        ),
        "actions_tpl": [
            "Add specific statistics with numbers (percentages, dollar amounts, counts)",
            "Include at least 1 data point per 200 words of content",
            "Attribute data to credible sources (industry reports, studies, official data)",
            "Add a data table or comparison chart with specific numbers",
            "Replace vague claims ('many companies') with specific data ('73% of B2B companies')",
        ],
        "effort_hours": 1.5,
        "priority_fn": lambda d: "medium",
    },
    "geo_no_answer_first": {
        "recommendation_type": "add_answer_first",
        "title_tpl": "Add TL;DR for AI extraction: {title}",
        "summary_tpl": (
            "The first 200 words don't directly answer the query implied by the title. "
            "AI systems extract the first passage that directly answers a prompt. "
            "Posts that front-load answers are cited 40% more often in AI Overviews."
        ),
        "actions_tpl": [
            "Add a TL;DR paragraph in the first 200 words that directly answers the title's question",
            "Include at least one specific data point in the opening",
            "Use declarative language: 'X is...' or 'The best way to Y is...'",
            "Don't start with a story, question, or background — lead with the answer",
            "The TL;DR should work as a standalone answer if extracted by AI",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "medium",
    },
    "geo_missing_faq_schema": {
        "recommendation_type": "add_faq_schema",
        "title_tpl": "Add FAQPage schema markup: {title}",
        "summary_tpl": (
            "This post has FAQ-like content but no FAQPage JSON-LD schema. "
            "Structured FAQ schema makes Q&A pairs directly extractable by AI systems "
            "and increases eligibility for Google rich results."
        ),
        "actions_tpl": [
            "Add FAQPage JSON-LD schema wrapping your FAQ section's Q&A pairs",
            "Each Question should have a corresponding acceptedAnswer",
            "Validate the schema at schema.org/validator",
            "Ensure the schema Q&A pairs exactly match the visible FAQ content",
        ],
        "effort_hours": 0.5,
        "priority_fn": lambda d: "high",
    },
    "geo_no_freshness_date": {
        "recommendation_type": "add_freshness_signal",
        "title_tpl": "Add visible update date: {title}",
        "summary_tpl": (
            "No visible 'Last updated' timestamp detected. AI systems favor content with "
            "recent modification dates. Posts older than 6 months without a visible update "
            "date are 3x less likely to be cited by AI."
        ),
        "actions_tpl": [
            "Add a visible 'Last updated: [date]' element near the top of the post",
            "Use a <time datetime='YYYY-MM-DD'> HTML element for machine readability",
            "Update the dateModified field in your Article JSON-LD schema",
            "Actually update the content when you update the date — AI systems cross-check",
        ],
        "effort_hours": 0.25,
        "priority_fn": lambda d: "low",
    },
}


async def generate_fast_recommendations(
    db: asyncpg.Connection,
    site_id: UUID,
) -> int:
    """Generate template-based recommendations for all detected problems.

    Returns the number of recommendations generated.
    """
    logger.info("Generating fast template-based recommendations for site %s", site_id)

    # Clear old recommendations
    await db.execute("DELETE FROM recommendations WHERE site_id = $1", site_id)

    # Fetch problems with post details
    # Exclude very short pages (<100 words) — these are tool pages, redirects, index pages
    # not actual blog content we can give recommendations on
    problems = await db.fetch("""
        SELECT cp.id as problem_id, cp.post_id, cp.problem_type, cp.severity, cp.details,
               p.title, p.word_count, p.url, p.readability_score, p.content_intent, p.language
        FROM content_problems cp
        JOIN posts p ON p.id = cp.post_id
        WHERE cp.site_id = $1
          AND (p.word_count IS NULL OR p.word_count >= 100)
        ORDER BY
            CASE cp.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            cp.problem_type
    """, site_id)

    # Fetch cluster averages for context
    cluster_avgs = await db.fetch("""
        SELECT c.id, c.label, avg(p.word_count) as avg_wc
        FROM clusters c
        JOIN post_clusters pc ON pc.cluster_id = c.id
        JOIN posts p ON p.id = pc.post_id
        WHERE c.site_id = $1
        GROUP BY c.id, c.label
    """, site_id)
    cluster_avg_map = {r["id"]: r["avg_wc"] for r in cluster_avgs}

    # Build post→cluster mapping
    post_clusters = await db.fetch("""
        SELECT pc.post_id, pc.cluster_id, c.label as cluster_label
        FROM post_clusters pc
        JOIN clusters c ON c.id = pc.cluster_id
        WHERE c.site_id = $1
    """, site_id)
    post_cluster_map: dict[UUID, tuple[UUID, str, float]] = {}
    for pc in post_clusters:
        cid = pc["cluster_id"]
        avg_wc = cluster_avg_map.get(cid, 1500)
        # Keep the one with highest avg (most relevant context)
        if pc["post_id"] not in post_cluster_map or avg_wc > post_cluster_map[pc["post_id"]][2]:
            post_cluster_map[pc["post_id"]] = (cid, pc["cluster_label"], avg_wc)

    recs_to_insert = []
    seen_post_types: set[tuple[UUID, str]] = set()  # Dedup: one rec per post per type

    for prob in problems:
        ptype = prob["problem_type"]
        post_id = prob["post_id"]

        # Skip if we already have a rec for this post+type
        key = (post_id, ptype)
        if key in seen_post_types:
            continue
        seen_post_types.add(key)

        template = _TEMPLATES.get(ptype)
        if not template:
            continue

        # Build context dict for template formatting
        details = prob["details"] if isinstance(prob["details"], dict) else {}
        cluster_info = post_cluster_map.get(post_id, (None, "Unknown", 1500))
        cluster_avg = int(cluster_info[2])
        word_count = prob["word_count"] if prob["word_count"] is not None else 0

        ctx = {
            "title": (prob["title"] or "Untitled")[:80],
            "word_count": word_count,
            "url": prob["url"],
            "threshold": details.get("threshold", 500),
            "content_type": prob["content_intent"] or "general",
            "target_words": max(cluster_avg, details.get("threshold", 500)),
            "words_needed": max(0, cluster_avg - word_count),
            "cluster_avg": cluster_avg,
            "title_length": len(prob["title"] or ""),
            "readability_score": prob["readability_score"] or 0,
            # AI-era fields (from problem details metadata)
            "citability_score": int(details.get("citability_score", 0)),
            "eeat_score": int(details.get("eeat_score", 0)),
            "schema_score": int(details.get("schema_score", 0)),
            "extraction_score": int(details.get("extraction_score", 0)),
        }

        try:
            title = template["title_tpl"].format(**ctx)
            # Support both static templates (summary_tpl) and dynamic functions (summary_fn)
            if "summary_fn" in template:
                summary = template["summary_fn"](ctx)
            else:
                summary = template["summary_tpl"].format(**ctx)
            if "actions_fn" in template:
                actions = template["actions_fn"](ctx)
            else:
                actions = [a.format(**ctx) for a in template["actions_tpl"]]
            priority = template["priority_fn"](ctx)
        except (KeyError, ValueError) as e:
            logger.warning("Template error for %s on %s: %s", ptype, post_id, e)
            continue

        # Confidence: high for objective issues (thin content, schema, orphan)
        # medium for contextual recommendations, low for structural suggestions
        _high_conf_types = {"thin_content", "seo_missing_meta", "orphan", "missing_schema",
                             "seo_no_images", "seo_title_length"}
        _med_conf_types = {"readability_too_complex", "thin_below_cluster_avg",
                           "improve_ai_citability", "poor_ai_structure"}
        confidence = (
            "high" if ptype in _high_conf_types else
            "medium" if ptype in _med_conf_types else
            "low"
        )

        recs_to_insert.append((
            post_id,                            # post_id
            site_id,                            # site_id
            prob["problem_id"],                 # problem_id
            template["recommendation_type"],    # recommendation_type
            priority,                           # priority
            template["effort_hours"],           # estimated_effort_hours
            "medium",                           # estimated_impact
            title,                              # title
            summary,                            # summary
            actions,                            # specific_actions (jsonb)
            None,                               # ai_generated_content
            confidence,                         # confidence
        ))

    # ── Cannibalization recommendations ──
    cann_pairs = await db.fetch("""
        SELECT cp.id, cp.post_a_id, cp.post_b_id, cp.cosine_similarity, cp.severity,
               cp.cluster_id,
               pa.title as title_a, pa.url as url_a, pa.word_count as wc_a,
               pa.language as lang_a,
               pb.title as title_b, pb.url as url_b, pb.word_count as wc_b,
               pb.language as lang_b
        FROM cannibalization_pairs cp
        JOIN posts pa ON pa.id = cp.post_a_id
        JOIN posts pb ON pb.id = cp.post_b_id
        WHERE pa.site_id = $1
          AND (pa.word_count IS NULL OR pa.word_count >= 100)
          AND (pb.word_count IS NULL OR pb.word_count >= 100)
          AND (pa.language IS NULL OR pb.language IS NULL OR pa.language = pb.language)
        ORDER BY cp.cosine_similarity DESC
    """, site_id)

    seen_cann: set[tuple[UUID, UUID]] = set()
    for pair in cann_pairs:
        pair_key = (min(pair["post_a_id"], pair["post_b_id"]), max(pair["post_a_id"], pair["post_b_id"]))
        if pair_key in seen_cann:
            continue
        seen_cann.add(pair_key)

        cos = pair["cosine_similarity"]
        wc_a = pair["wc_a"] or 0
        wc_b = pair["wc_b"] or 0

        if cos >= 0.99:
            # Near-identical — redirect
            keep = "A" if wc_a >= wc_b else "B"
            redirect = "B" if keep == "A" else "A"
            keep_url = pair[f"url_{keep.lower()}"]
            redirect_url = pair[f"url_{redirect.lower()}"]
            title = f"Redirect duplicate: {pair[f'title_{redirect.lower()}'][:50]}"
            summary = f"These two posts are near-identical (cosine={cos:.3f}). Set up a 301 redirect from the weaker post to the stronger one."
            actions = [
                f"301 redirect {redirect_url} → {keep_url}",
                "Merge any unique content from the redirected post into the kept post",
                "Update any internal links pointing to the old URL",
            ]
            priority = "critical"
            effort = 0.5
        elif cos >= 0.90:
            # Very similar — merge
            keep = "A" if wc_a >= wc_b else "B"
            merge = "B" if keep == "A" else "A"
            title = f"Merge overlapping content: {pair[f'title_{keep.lower()}'][:50]}"
            summary = f"These posts overlap significantly (cosine={cos:.3f}). Merge unique sections from the shorter post into the longer one, then redirect."
            actions = [
                "Compare both posts section by section",
                f"Move unique paragraphs from '{pair[f'title_{merge.lower()}'][:40]}' into '{pair[f'title_{keep.lower()}'][:40]}'",
                "301 redirect the merged post to the consolidated one",
                "Update internal links",
            ]
            priority = "high"
            effort = 2.0
        else:
            # Moderate overlap — differentiate
            title = f"Differentiate competing content: {pair['title_a'][:50]}"
            summary = f"These posts have significant topic overlap (cosine={cos:.3f}). Differentiate by targeting distinct keywords and angles."
            actions = [
                "Identify the unique angle for each post",
                "Adjust titles and H1s to target different keyword variants",
                "Cross-link between the two posts with descriptive anchor text",
                "Consider making one a 'beginner' guide and the other 'advanced'",
            ]
            priority = "medium"
            effort = 1.5

        # Store cluster_id + redirect info in ai_generated_content so the
        # UI can deep-link to consolidation flow and show redirect downloads
        import json as _json
        cann_ai_content = _json.dumps({
            "cluster_id": str(pair["cluster_id"]) if pair["cluster_id"] else None,
            "post_a_url": pair["url_a"],
            "post_b_url": pair["url_b"],
            "cosine_similarity": round(cos, 3),
        })

        recs_to_insert.append((
            pair["post_a_id"], site_id, None, "merge" if cos >= 0.90 else "differentiate",
            priority, effort, "high" if cos >= 0.90 else "medium",
            title, summary, actions, cann_ai_content,
            "high" if cos >= 0.85 else "medium",  # confidence
        ))

    # ── Link suggestion recommendations — candidate-aware orphan recs ──
    # Use pgvector similarity to find the most relevant existing posts to link FROM
    orphan_posts = await db.fetch("""
        SELECT p.id, p.title, p.url, pe.embedding
        FROM posts p
        JOIN post_embeddings pe ON pe.post_id = p.id
        WHERE p.site_id = $1
        AND p.id NOT IN (
            SELECT DISTINCT target_post_id FROM internal_links
            WHERE target_post_id IS NOT NULL
        )
        LIMIT 20
    """, site_id)

    for orphan in orphan_posts:
        # Find 5 most similar posts that already have inbound links (good link sources)
        link_sources = await db.fetch("""
            SELECT p.id, p.title, p.url,
                   1 - (pe.embedding <=> $2::vector) AS similarity
            FROM posts p
            JOIN post_embeddings pe ON pe.post_id = p.id
            WHERE p.site_id = $1
              AND p.id != $3
              AND p.id IN (
                  SELECT DISTINCT source_post_id FROM internal_links WHERE site_id = $1
              )
            ORDER BY pe.embedding <=> $2::vector
            LIMIT 5
        """, site_id, orphan["embedding"], orphan["id"])

        if not link_sources:
            continue

        source_list = [
            f"• \"{s['title'][:55]}\" — use anchor text related to the orphan topic"
            for s in link_sources[:3]
        ]
        actions = [
            "This post has 0 inbound internal links — it won't be crawled or ranked effectively.",
            "Add a contextual link from these highly relevant posts:",
            *source_list,
            "Aim for anchor text that describes the target topic, not generic 'click here'.",
        ]

        # Store specific link targets from RAG (pgvector similarity) in
        # ai_generated_content so the UI can show exact posts + anchor text
        import json as _json
        link_targets_data = _json.dumps({
            "link_targets": [
                {
                    "post_id": str(s["id"]),
                    "title": s["title"],
                    "url": s["url"],
                    "similarity": round(float(s["similarity"]), 2),
                    "suggested_anchor": orphan["title"].lower()[:60],
                }
                for s in link_sources[:5]
            ]
        })

        key = (orphan["id"], "interlink")
        if key not in seen_post_types:
            seen_post_types.add(key)
            recs_to_insert.append((
                orphan["id"], site_id, None, "interlink",
                "high", 0.5, "medium",
                f"Fix orphan: {orphan['title'][:60]}",
                f"This post has no inbound internal links. Link to it from {len(link_sources)} related posts that cover similar topics.",
                actions, link_targets_data,
                "high",  # confidence — orphan detection is 100% objective
            ))

    # ── Batch insert ──
    if recs_to_insert:
        await db.executemany("""
            INSERT INTO recommendations
                (post_id, site_id, problem_id, recommendation_type, priority,
                 estimated_effort_hours, estimated_impact, title, summary,
                 specific_actions, ai_generated_content, confidence)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12)
            ON CONFLICT DO NOTHING
        """, [
            (*r[:9], __import__("json").dumps(r[9]) if r[9] else None, r[10],
             r[11] if len(r) > 11 else "medium")
            for r in recs_to_insert
        ])

    logger.info(
        "Fast recommendations: %d generated for site %s (problems=%d, cann=%d, interlink=%d)",
        len(recs_to_insert), site_id,
        sum(1 for r in recs_to_insert if r[3] in ("expand", "optimize")),
        sum(1 for r in recs_to_insert if r[3] in ("merge", "differentiate")),
        sum(1 for r in recs_to_insert if r[3] == "interlink"),
    )

    return len(recs_to_insert)
