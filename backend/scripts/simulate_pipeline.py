#!/usr/bin/env python3
"""Simulate the full Tended intelligence pipeline with realistic blog data.

No external dependencies needed — runs entirely locally with synthetic data
to demonstrate what the system produces at each stage.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from uuid import uuid4

# Add parent dir so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.health_scoring import (
    _compute_trend, _ranking_score, _engagement_score,
    _freshness_score, _content_depth_score, _technical_seo_score,
    _assign_role, _assign_ecosystem_state,
)

NOW = datetime.now(timezone.utc)

# ═══════════════════════════════════════════════
# STEP 1: Fake blog — "TechStartupBlog.com"
# A SaaS blog with 12 posts across 3 topic clusters
# ═══════════════════════════════════════════════

POSTS = [
    # ── Cluster 1: "SaaS Pricing" (4 posts) ──
    {
        "id": "post-1", "title": "The Ultimate Guide to SaaS Pricing Models in 2024",
        "url": "https://techstartupblog.com/saas-pricing-models/",
        "word_count": 3200, "publish_date": NOW - timedelta(days=60),
        "modified_date": NOW - timedelta(days=15),
        "headings": [{"level": "h2", "text": "Flat-Rate Pricing"}, {"level": "h2", "text": "Usage-Based Pricing"}, {"level": "h2", "text": "Tiered Pricing"}, {"level": "h3", "text": "Which Model Works Best"}],
        "meta_description": "Compare flat-rate, usage-based, and tiered SaaS pricing models. Data-driven guide with real examples from 50+ SaaS companies.",
        "has_images": True,
        "recent_pv": 2800, "prev_pv": 2400, "total_60d_pv": 5200,
        "avg_position": 3.2, "bounce_rate": 0.32, "avg_time": 185.0,
        "inbound_links": 8, "outbound_links": 5,
        "queries": {"saas pricing models", "saas pricing strategy", "saas pricing guide", "how to price saas"},
    },
    {
        "id": "post-2", "title": "How to Price Your SaaS Product: A Step-by-Step Framework",
        "url": "https://techstartupblog.com/how-to-price-saas/",
        "word_count": 2800, "publish_date": NOW - timedelta(days=180),
        "modified_date": NOW - timedelta(days=180),
        "headings": [{"level": "h2", "text": "Step 1: Research"}, {"level": "h2", "text": "Step 2: Calculate Costs"}, {"level": "h2", "text": "Step 3: Test Prices"}],
        "meta_description": "Step-by-step framework for pricing your SaaS product. Includes cost calculators and real pricing experiments.",
        "has_images": True,
        "recent_pv": 1200, "prev_pv": 1800, "total_60d_pv": 3000,
        "avg_position": 7.8, "bounce_rate": 0.45, "avg_time": 140.0,
        "inbound_links": 5, "outbound_links": 3,
        "queries": {"how to price saas", "saas pricing framework", "saas pricing strategy", "price saas product"},
    },
    {
        "id": "post-3", "title": "SaaS Pricing Page Examples That Convert",
        "url": "https://techstartupblog.com/saas-pricing-page-examples/",
        "word_count": 1800, "publish_date": NOW - timedelta(days=400),
        "modified_date": NOW - timedelta(days=400),
        "headings": [{"level": "h2", "text": "Best Pricing Pages"}, {"level": "h2", "text": "Common Mistakes"}],
        "meta_description": None,
        "has_images": True,
        "recent_pv": 400, "prev_pv": 900, "total_60d_pv": 1300,
        "avg_position": 18.5, "bounce_rate": 0.65, "avg_time": 55.0,
        "inbound_links": 1, "outbound_links": 2,
        "queries": {"saas pricing page examples", "pricing page design", "saas pricing page"},
    },
    {
        "id": "post-4", "title": "Pricing",
        "url": "https://techstartupblog.com/pricing/",
        "word_count": 280, "publish_date": NOW - timedelta(days=500),
        "modified_date": NOW - timedelta(days=500),
        "headings": [],
        "meta_description": None,
        "has_images": False,
        "recent_pv": 50, "prev_pv": 80, "total_60d_pv": 130,
        "avg_position": 45.0, "bounce_rate": 0.88, "avg_time": 12.0,
        "inbound_links": 0, "outbound_links": 0,
        "queries": set(),
    },

    # ── Cluster 2: "Customer Onboarding" (4 posts) ──
    {
        "id": "post-5", "title": "Customer Onboarding Best Practices for SaaS Companies",
        "url": "https://techstartupblog.com/customer-onboarding-best-practices/",
        "word_count": 2500, "publish_date": NOW - timedelta(days=90),
        "modified_date": NOW - timedelta(days=30),
        "headings": [{"level": "h2", "text": "Welcome Emails"}, {"level": "h2", "text": "Product Tours"}, {"level": "h2", "text": "Milestone Tracking"}, {"level": "h3", "text": "Tools"}],
        "meta_description": "12 proven onboarding best practices used by top SaaS companies. Reduce churn by 23% with these strategies.",
        "has_images": True,
        "recent_pv": 1500, "prev_pv": 1300, "total_60d_pv": 2800,
        "avg_position": 5.5, "bounce_rate": 0.38, "avg_time": 160.0,
        "inbound_links": 6, "outbound_links": 4,
        "queries": {"customer onboarding best practices", "saas onboarding", "onboarding strategy"},
    },
    {
        "id": "post-6", "title": "How to Build a SaaS Onboarding Flow",
        "url": "https://techstartupblog.com/saas-onboarding-flow/",
        "word_count": 2200, "publish_date": NOW - timedelta(days=120),
        "modified_date": NOW - timedelta(days=120),
        "headings": [{"level": "h2", "text": "Map the Journey"}, {"level": "h2", "text": "Design Checkpoints"}],
        "meta_description": "Build an onboarding flow that reduces time-to-value. Complete guide with Figma templates.",
        "has_images": True,
        "recent_pv": 800, "prev_pv": 750, "total_60d_pv": 1550,
        "avg_position": 9.2, "bounce_rate": 0.42, "avg_time": 130.0,
        "inbound_links": 3, "outbound_links": 3,
        "queries": {"saas onboarding flow", "onboarding flow design", "saas onboarding"},
    },
    {
        "id": "post-7", "title": "Onboarding Email Sequences That Work",
        "url": "https://techstartupblog.com/onboarding-email-sequences/",
        "word_count": 1600, "publish_date": NOW - timedelta(days=200),
        "modified_date": NOW - timedelta(days=200),
        "headings": [{"level": "h2", "text": "Day 1 Email"}, {"level": "h2", "text": "Day 3 Email"}, {"level": "h2", "text": "Day 7 Email"}],
        "meta_description": "Copy-paste onboarding email templates. 7-day sequence with subject lines and copy.",
        "has_images": False,
        "recent_pv": 600, "prev_pv": 600, "total_60d_pv": 1200,
        "avg_position": 12.0, "bounce_rate": 0.50, "avg_time": 95.0,
        "inbound_links": 2, "outbound_links": 1,
        "queries": {"onboarding email sequence", "onboarding emails", "saas welcome email"},
    },
    {
        "id": "post-8", "title": "Why Users Churn During Onboarding (And How to Fix It)",
        "url": "https://techstartupblog.com/onboarding-churn/",
        "word_count": 1900, "publish_date": NOW - timedelta(days=45),
        "modified_date": NOW - timedelta(days=45),
        "headings": [{"level": "h2", "text": "Top 5 Churn Reasons"}, {"level": "h2", "text": "Fix #1"}, {"level": "h2", "text": "Fix #2"}],
        "meta_description": "Why 40% of users churn in the first week — and 5 fixes backed by data from 200 SaaS companies.",
        "has_images": True,
        "recent_pv": 950, "prev_pv": 400, "total_60d_pv": 1350,
        "avg_position": 6.8, "bounce_rate": 0.35, "avg_time": 155.0,
        "inbound_links": 4, "outbound_links": 3,
        "queries": {"onboarding churn", "reduce churn saas", "why users churn"},
    },

    # ── Cluster 3: "Cold Email" (3 posts — all declining) ──
    {
        "id": "post-9", "title": "Cold Email Templates for B2B SaaS",
        "url": "https://techstartupblog.com/cold-email-templates/",
        "word_count": 2000, "publish_date": NOW - timedelta(days=600),
        "modified_date": NOW - timedelta(days=600),
        "headings": [{"level": "h2", "text": "Template 1"}, {"level": "h2", "text": "Template 2"}],
        "meta_description": "10 cold email templates that got replies in 2022.",
        "has_images": False,
        "recent_pv": 150, "prev_pv": 500, "total_60d_pv": 650,
        "avg_position": 22.0, "bounce_rate": 0.72, "avg_time": 40.0,
        "inbound_links": 1, "outbound_links": 0,
        "queries": {"cold email templates b2b", "cold email saas"},
    },
    {
        "id": "post-10", "title": "How to Write Cold Emails That Get Replies",
        "url": "https://techstartupblog.com/cold-email-tips/",
        "word_count": 1500, "publish_date": NOW - timedelta(days=550),
        "modified_date": NOW - timedelta(days=550),
        "headings": [{"level": "h2", "text": "Subject Lines"}, {"level": "h2", "text": "Body Copy"}],
        "meta_description": "7 tips for cold emails that actually get replies. Based on sending 10,000 cold emails.",
        "has_images": False,
        "recent_pv": 80, "prev_pv": 300, "total_60d_pv": 380,
        "avg_position": 28.0, "bounce_rate": 0.78, "avg_time": 30.0,
        "inbound_links": 0, "outbound_links": 1,
        "queries": {"cold email tips", "cold email best practices", "cold email saas"},
    },
    {
        "id": "post-11", "title": "Cold Outreach",
        "url": "https://techstartupblog.com/cold-outreach/",
        "word_count": 350, "publish_date": NOW - timedelta(days=700),
        "modified_date": NOW - timedelta(days=700),
        "headings": [],
        "meta_description": None,
        "has_images": False,
        "recent_pv": 3, "prev_pv": 2, "total_60d_pv": 5,
        "avg_position": 55.0, "bounce_rate": 0.92, "avg_time": 8.0,
        "inbound_links": 0, "outbound_links": 0,
        "queries": set(),
    },

    # ── Unclustered: Recent post ──
    {
        "id": "post-12", "title": "AI-Powered Customer Support: The Complete Guide for 2025",
        "url": "https://techstartupblog.com/ai-customer-support/",
        "word_count": 4200, "publish_date": NOW - timedelta(days=7),
        "modified_date": NOW - timedelta(days=7),
        "headings": [{"level": "h2", "text": "Chatbots"}, {"level": "h2", "text": "Ticket Routing"}, {"level": "h2", "text": "Knowledge Bases"}, {"level": "h3", "text": "Tools Comparison"}],
        "meta_description": "Complete guide to AI customer support in 2025. Compare 15 tools, implementation strategies, and ROI metrics.",
        "has_images": True,
        "recent_pv": 3500, "prev_pv": 0, "total_60d_pv": 3500,
        "avg_position": 4.0, "bounce_rate": 0.28, "avg_time": 210.0,
        "inbound_links": 2, "outbound_links": 6,
        "queries": {"ai customer support", "ai support tools", "ai helpdesk"},
    },
]

CLUSTERS = {
    "SaaS Pricing": ["post-1", "post-2", "post-3", "post-4"],
    "Customer Onboarding": ["post-5", "post-6", "post-7", "post-8"],
    "Cold Email Outreach": ["post-9", "post-10", "post-11"],
}


def score_post(post, cluster_avg_wc, max_inbound):
    """Score a single post using the 7-factor model."""
    trend, trend_score = _compute_trend(post["recent_pv"], post["prev_pv"], post["total_60d_pv"])
    ranking = _ranking_score(post["avg_position"])
    engagement = _engagement_score(post["bounce_rate"], post["avg_time"])
    freshness = _freshness_score(post["modified_date"], NOW)
    depth = _content_depth_score(post["word_count"], cluster_avg_wc)
    links = min(100.0, (post["inbound_links"] / max(max_inbound, 1)) * 100.0)
    tech_seo = _technical_seo_score(
        post["meta_description"], post["title"],
        post["headings"], post["outbound_links"] > 0,
        post["inbound_links"] > 0,
    )
    composite = (
        0.25 * trend_score + 0.20 * ranking + 0.15 * engagement +
        0.15 * freshness + 0.10 * depth + 0.10 * links + 0.05 * tech_seo
    )
    return {
        "composite": round(composite, 1),
        "trend": trend, "trend_score": round(trend_score, 1),
        "ranking": round(ranking, 1), "engagement": round(engagement, 1),
        "freshness": round(freshness, 1), "depth": round(depth, 1),
        "links": round(links, 1), "tech_seo": round(tech_seo, 1),
    }


def detect_cannibalization(cluster_posts):
    """Detect cannibalization by query overlap."""
    pairs = []
    for i, a in enumerate(cluster_posts):
        for b in cluster_posts[i+1:]:
            shared = a["queries"] & b["queries"]
            if shared:
                pairs.append((a, b, shared))
    return pairs


def detect_problems(post, cluster_avg_wc, scores):
    """Detect all problems for a post."""
    problems = []
    # Decay
    if post["prev_pv"] > 10 and post["recent_pv"] < post["prev_pv"] * 0.7:
        drop_pct = round((post["prev_pv"] - post["recent_pv"]) / post["prev_pv"] * 100, 1)
        problems.append(("decay", f"Clicks dropped {drop_pct}% (was {post['prev_pv']}, now {post['recent_pv']})"))
    # Thin
    if post["word_count"] < 500:
        problems.append(("thin_content", f"Only {post['word_count']} words (min recommended: 500)"))
    if cluster_avg_wc > 500 and post["word_count"] < cluster_avg_wc * 0.5:
        problems.append(("thin_below_avg", f"{post['word_count']} words vs cluster avg {round(cluster_avg_wc)}"))
    # High bounce + low time
    if post["bounce_rate"] > 0.8 and post["avg_time"] < 30:
        problems.append(("thin_bounce", f"Bounce {round(post['bounce_rate']*100)}% + avg time {round(post['avg_time'])}s"))
    # SEO
    if not post["meta_description"]:
        problems.append(("seo_no_meta", "Missing meta description"))
    title_len = len(post["title"])
    if title_len < 30 or title_len > 60:
        problems.append(("seo_title", f"Title is {title_len} chars (ideal: 30-60)"))
    if not post["headings"]:
        problems.append(("seo_no_headings", "No H2/H3 headings"))
    if post["inbound_links"] == 0 and post["outbound_links"] == 0:
        problems.append(("seo_no_links", "No internal links to or from this post"))
    if not post.get("has_images"):
        problems.append(("seo_no_images", "No images in content"))
    # Orphan
    if post["inbound_links"] == 0:
        problems.append(("orphan", "Zero inbound internal links — orphan content"))
    return problems


def main():
    print("=" * 70)
    print("  TENDED — Full Pipeline Simulation")
    print("  Blog: TechStartupBlog.com (12 posts, 3 clusters)")
    print("=" * 70)

    # ── STEP 1: Clustering ──
    print("\n\n📊 STEP 1: CLUSTERING (UMAP + HDBSCAN)")
    print("-" * 50)
    for cluster_name, post_ids in CLUSTERS.items():
        posts = [p for p in POSTS if p["id"] in post_ids]
        print(f"\n  🏷️  Cluster: \"{cluster_name}\"")
        print(f"  📝 Posts: {len(posts)}")
        for p in posts:
            print(f"     • {p['title'][:55]}... ({p['word_count']} words)")

    # ── STEP 2: Health Scoring ──
    print("\n\n🩺 STEP 2: HEALTH SCORING (7-Factor Model)")
    print("-" * 50)

    all_scores = {}
    for cluster_name, post_ids in CLUSTERS.items():
        posts = [p for p in POSTS if p["id"] in post_ids]
        cluster_avg_wc = sum(p["word_count"] for p in posts) / len(posts)
        max_inbound = max(p["inbound_links"] for p in posts) or 1

        print(f"\n  🌿 Cluster: \"{cluster_name}\" (avg {round(cluster_avg_wc)} words)")
        for p in posts:
            scores = score_post(p, cluster_avg_wc, max_inbound)
            all_scores[p["id"]] = scores

            # Determine role
            traffic_contrib = p["recent_pv"] / max(sum(pp["recent_pv"] for pp in posts), 1)
            cannibalizing = False
            for other in posts:
                if other["id"] != p["id"] and p["queries"] & other["queries"]:
                    cannibalizing = True
                    break
            role = _assign_role(scores["composite"], traffic_contrib, p["recent_pv"], cannibalizing)

            print(f"\n     📄 {p['title'][:50]}")
            print(f"        Composite: {scores['composite']}/100 | Role: {role.upper()}")
            print(f"        Trend: {scores['trend']} ({scores['trend_score']}) | Ranking: {scores['ranking']}")
            print(f"        Engagement: {scores['engagement']} | Freshness: {scores['freshness']}")
            print(f"        Depth: {scores['depth']} | Links: {scores['links']} | SEO: {scores['tech_seo']}")

    # ── STEP 3: Cannibalization ──
    print("\n\n⚔️  STEP 3: CANNIBALIZATION DETECTION")
    print("-" * 50)
    for cluster_name, post_ids in CLUSTERS.items():
        posts = [p for p in POSTS if p["id"] in post_ids]
        pairs = detect_cannibalization(posts)
        if pairs:
            print(f"\n  🔴 Cluster: \"{cluster_name}\"")
            for a, b, shared in pairs:
                print(f"     ⚔️  PAIR:")
                print(f"        A: {a['title'][:50]}")
                print(f"        B: {b['title'][:50]}")
                print(f"        Shared queries: {', '.join(sorted(shared))}")

    # ── STEP 4: Problem Detection ──
    print("\n\n🔍 STEP 4: PROBLEM DETECTION")
    print("-" * 50)
    total_problems = 0
    problem_posts = {}
    for cluster_name, post_ids in CLUSTERS.items():
        posts = [p for p in POSTS if p["id"] in post_ids]
        cluster_avg_wc = sum(p["word_count"] for p in posts) / len(posts)
        for p in posts:
            problems = detect_problems(p, cluster_avg_wc, all_scores.get(p["id"], {}))
            if problems:
                problem_posts[p["id"]] = problems
                total_problems += len(problems)
                print(f"\n     📄 {p['title'][:50]}")
                for ptype, desc in problems:
                    icon = {"decay": "📉", "thin": "📏", "seo": "🔧", "orphan": "🏝️"}.get(ptype.split("_")[0], "⚠️")
                    print(f"        {icon} [{ptype}] {desc}")

    print(f"\n  Total: {total_problems} problems across {len(problem_posts)} posts")

    # ── STEP 5: AI Recommendations ──
    print("\n\n🤖 STEP 5: AI RECOMMENDATIONS")
    print("=" * 70)
    print("(These are examples of what Claude would generate for each problem type)")
    print("=" * 70)

    # Example 1: Cannibalization
    print("""
┌──────────────────────────────────────────────────────────────────────┐
│  ⚔️  CANNIBALIZATION RECOMMENDATION                                 │
│  Posts: "Ultimate Guide to SaaS Pricing" vs "How to Price Your SaaS"│
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  🏆 PRIMARY POST (keep): "Ultimate Guide to SaaS Pricing Models"    │
│     Reason: Higher traffic (2800 vs 1200 clicks/mo), better         │
│     ranking (pos 3.2 vs 7.8), more comprehensive (3200 vs 2800      │
│     words), more inbound links (8 vs 5).                            │
│                                                                      │
│  📋 MERGE FROM SECONDARY:                                           │
│  1. "Step-by-Step Framework" section — the primary lacks a          │
│     structured how-to framework. Merge the 3-step process           │
│     (Research → Calculate Costs → Test) as a new H2 section.        │
│  2. "Cost Calculator" methodology — primary covers models but       │
│     not actual cost calculation. Add as subsection under             │
│     "Which Model Works Best".                                       │
│  3. "Pricing Experiments" — real A/B test data from secondary.      │
│     Add as evidence throughout the primary post.                     │
│                                                                      │
│  ➕ NEW SECTIONS (neither post covers):                              │
│  1. "Psychology of SaaS Pricing" — anchoring, decoy pricing         │
│  2. "How to Handle Price Increases" — retention during changes      │
│  3. "Pricing for PLG vs Sales-Led" — missing strategic angle        │
│                                                                      │
│  🔄 REDIRECT STRATEGY:                                              │
│  301 redirect /how-to-price-saas/ → /saas-pricing-models/           │
│  Update 3 internal links pointing to the old URL.                   │
│  Monitor GSC for 30 days to verify ranking consolidation.           │
│                                                                      │
│  ⏱️  Effort: 3-4 hours | 📈 Impact: HIGH (recover ~1200 clicks/mo)  │
│  Priority: CRITICAL                                                  │
└──────────────────────────────────────────────────────────────────────┘""")

    # Example 2: Content Decay
    print("""
┌──────────────────────────────────────────────────────────────────────┐
│  📉 CONTENT DECAY RECOMMENDATION                                    │
│  Post: "SaaS Pricing Page Examples That Convert"                     │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  📊 DECAY SIGNAL: Clicks dropped 56% (900 → 400) in 90 days.       │
│  Was ranking position 8, now position 18.5.                          │
│  Last updated: 13 months ago.                                        │
│                                                                      │
│  🔴 OUTDATED SECTIONS:                                              │
│  1. "Best Pricing Pages" — references Basecamp's 2022 redesign     │
│     and Slack's old pricing (pre-Salesforce acquisition).            │
│     Needs 2024/2025 examples (Notion, Linear, Vercel).              │
│  2. "Common Mistakes" — lists "hiding the free tier" which is       │
│     now standard practice. Outdated advice.                          │
│                                                                      │
│  📝 FACTS TO UPDATE:                                                │
│  • "73% of SaaS companies use tiered pricing" → check 2025 data    │
│  • Screenshot of Stripe's pricing page is from 2022 redesign       │
│  • Missing: AI-powered dynamic pricing trend (new in 2024)          │
│                                                                      │
│  ➕ NEW SECTIONS TO ADD:                                             │
│  1. "AI-Powered Pricing Pages" — dynamic pricing, personalization  │
│  2. "Mobile-First Pricing Design" — 60% of traffic is mobile now   │
│  3. "Pricing Page A/B Tests" — real conversion data                 │
│  4. "Free vs Freemium Landing" — PLG pricing page patterns          │
│                                                                      │
│  🎯 TARGET KEYWORDS (from GSC):                                     │
│  Primary: "saas pricing page examples" (was pos 8, recoverable)     │
│  Secondary: "pricing page design", "saas pricing page"              │
│                                                                      │
│  📝 SUGGESTED NEW TITLE:                                            │
│  "15 SaaS Pricing Page Examples That Convert in 2025"               │
│  (adds number, recency, stays under 60 chars)                       │
│                                                                      │
│  ⏱️  Effort: 4-5 hours | 📈 Impact: HIGH (recover ~500 clicks/mo)   │
│  Priority: HIGH                                                      │
└──────────────────────────────────────────────────────────────────────┘""")

    # Example 3: Thin Content
    print("""
┌──────────────────────────────────────────────────────────────────────┐
│  📏 THIN CONTENT RECOMMENDATION                                     │
│  Post: "Pricing" (280 words)                                        │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  📊 DIAGNOSIS: 280 words vs cluster average of 2,020 words (14%).   │
│  No headings. No meta description. No images. No internal links.    │
│  Bounce rate: 88%. Average time on page: 12 seconds.                │
│                                                                      │
│  🎯 DECISION: CONSOLIDATE (not expand)                              │
│                                                                      │
│  Reason: This post overlaps heavily with "The Ultimate Guide to     │
│  SaaS Pricing Models" which already covers the same topic at 3200   │
│  words and ranks position 3.2. Expanding this thin post would       │
│  create MORE cannibalization, not less.                              │
│                                                                      │
│  📋 ACTION:                                                         │
│  1. Review the 280 words — extract any unique angles (there may     │
│     be a personal anecdote or unique framing worth keeping)          │
│  2. If anything unique exists, add it to the pillar post            │
│  3. 301 redirect /pricing/ → /saas-pricing-models/                  │
│  4. Remove from sitemap                                             │
│                                                                      │
│  ⏱️  Effort: 30 min | 📈 Impact: MEDIUM (reduce cannibalization)    │
│  Priority: HIGH                                                      │
└──────────────────────────────────────────────────────────────────────┘""")

    # Example 4: SEO Fix
    print("""
┌──────────────────────────────────────────────────────────────────────┐
│  🔧 SEO FIX RECOMMENDATION                                         │
│  Post: "SaaS Pricing Page Examples That Convert"                     │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Issue: Missing meta description                                     │
│                                                                      │
│  ✅ GENERATED META DESCRIPTION:                                      │
│  "See 15 real SaaS pricing page examples that drive conversions.    │
│  Analyze what makes Notion, Linear & Stripe's pages work — with     │
│  screenshots and teardowns."                                         │
│  (158 characters — within 150-160 target)                           │
│                                                                      │
│  Primary keyword: "saas pricing page examples"                       │
│  CTA element: "See" + "Analyze" (action verbs)                      │
│  Social proof: Named brands                                         │
│                                                                      │
│  ⏱️  Effort: 2 minutes | 📈 Impact: MEDIUM (improve CTR ~15-20%)    │
│  Priority: MEDIUM                                                    │
└──────────────────────────────────────────────────────────────────────┘""")

    # Example 5: Growth
    print("""
┌──────────────────────────────────────────────────────────────────────┐
│  🌱 GROWTH RECOMMENDATION                                          │
│  Pillar: "Customer Onboarding Best Practices" (score: 75/100)       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  This pillar post is performing well at position 5.5. Build a       │
│  topic cluster around it with these 3 supporting posts:             │
│                                                                      │
│  📝 POST 1: "Product-Led Onboarding: How to Let Your Product       │
│     Do the Selling"                                                  │
│     Target keyword: "product-led onboarding" (vol: 720/mo)          │
│     Outline:                                                         │
│     - What PLG onboarding looks like vs traditional                 │
│     - 5 PLG onboarding patterns (Notion, Figma, Canva)              │
│     - How to identify your "aha moment"                              │
│     - Measuring activation rate                                      │
│     Link to pillar: "For general onboarding best practices,         │
│     see our complete guide [link]"                                   │
│                                                                      │
│  📝 POST 2: "SaaS Onboarding Metrics: 8 KPIs You Should Track"    │
│     Target keyword: "onboarding metrics saas" (vol: 480/mo)         │
│     Outline:                                                         │
│     - Time-to-value (TTV)                                           │
│     - Activation rate by cohort                                      │
│     - Feature adoption curve                                         │
│     - Onboarding completion rate                                     │
│     Link to pillar: Reference best practices for each metric        │
│                                                                      │
│  📝 POST 3: "Enterprise vs SMB Onboarding: Different Playbooks"    │
│     Target keyword: "enterprise saas onboarding" (vol: 320/mo)      │
│     Outline:                                                         │
│     - White-glove vs self-serve spectrum                             │
│     - Implementation timelines                                       │
│     - Stakeholder management                                         │
│     - CSM handoff process                                            │
│     Link to pillar: "These principles adapt our core best           │
│     practices [link] for enterprise contexts"                        │
│                                                                      │
│  ⏱️  Effort: 15-20 hours | 📈 Impact: HIGH (3 new ranking pages)    │
│  Priority: MEDIUM                                                    │
└──────────────────────────────────────────────────────────────────────┘""")

    # ── STEP 6: Ecosystem State ──
    print("\n\n🌍 ECOSYSTEM STATE SUMMARY")
    print("=" * 70)
    print("""
  🌲 "SaaS Pricing" → SWAMP
     Has a pillar (post-1) but heavy cannibalization between post-1 and
     post-2 (3 shared queries). Post-4 is dead weight. Needs cleanup.

  🌻 "Customer Onboarding" → FOREST
     Healthy pillar (post-5), growing post (post-8), low cannibalization,
     good internal linking. This is how a cluster should look.

  🏜️  "Cold Email Outreach" → DESERT
     All posts declining. Post-11 is dead (5 clicks/60d). Content is
     18+ months old. Either revive with major updates or accept the
     decline and redirect traffic to stronger clusters.
""")

    print("\n📊 SITE-WIDE METRICS")
    print("-" * 50)
    print(f"  Total posts: 12")
    print(f"  Active (growing/stable): 7")
    print(f"  Declining: 4")
    print(f"  Dead: 1")
    print(f"  Cannibalization pairs: 3")
    print(f"  Orphan posts: 3")
    print(f"  Problems detected: {total_problems}")
    print(f"  Recommendations generated: ~15")
    print(f"\n  Overall content health: 52/100")
    print(f"  Content efficiency ratio: 58%")
    print(f"  (7 of 12 posts are pulling their weight)")


if __name__ == "__main__":
    main()
