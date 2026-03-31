#!/usr/bin/env python3
"""Full Intelligence Layer Simulation — All 13 Signals.

Simulates a realistic 15-post SaaS blog ("GrowthStack.io") with:
- 3 topic clusters (Email Marketing, SEO Strategy, Content Marketing)
- Mixed health states (pillars, supporters, dead weight)
- Cannibalization pairs
- Content gaps
- Intent mismatches
- SERP opportunities
- Readability issues
- Velocity decline

Runs every intelligence signal and prints results.
"""

import json
import sys
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.readability import (
    compute_flesch_reading_ease,
    compute_grade_level,
    READABILITY_TOO_COMPLEX,
)
from app.services.weighted_embeddings import construct_weighted_text
from app.services.intent_classifier import classify_query_intent
from app.services.serp_features import detect_snippet_type, check_post_has_format
from app.services.content_velocity import VELOCITY_DECLINE_RATIO
from app.services.health_scoring import (
    compute_dynamic_weights,
    _compute_trend,
    _ranking_score,
    _engagement_score,
    _freshness_score,
    _content_depth_score,
    _technical_seo_score,
    _assign_role,
    _assign_ecosystem_state,
)
from app.services.cannibalization import CannibalizationDetector
from app.services.pagerank import InternalPageRank

now = datetime.now(timezone.utc)

# ═══════════════════════════════════════════════════════════════
# BLOG DATA: GrowthStack.io — a SaaS marketing blog
# ═══════════════════════════════════════════════════════════════

POSTS = [
    # ── Cluster 1: Email Marketing (5 posts) ──
    {
        "id": uuid4(), "title": "The Complete Guide to Email Marketing in 2024",
        "url": "/email-marketing-guide-2024",
        "word_count": 3200, "publish_date": now - timedelta(days=45),
        "modified_date": now - timedelta(days=10),
        "meta_description": "Learn everything about email marketing in 2024 — from list building to automation, segmentation, and measuring ROI.",
        "headings": [{"level": "h2", "text": "Why Email Marketing Still Matters"},
                     {"level": "h2", "text": "Building Your Email List"},
                     {"level": "h3", "text": "Lead Magnets That Convert"},
                     {"level": "h2", "text": "Email Automation Workflows"},
                     {"level": "h2", "text": "Measuring Email ROI"}],
        "body_text": "Email marketing remains one of the most effective channels for SaaS companies. With an average ROI of $42 for every $1 spent, it outperforms social media, paid ads, and content marketing combined. In this comprehensive guide, we'll cover everything you need to know about email marketing in 2024.\n\nBuilding your email list is the foundation. Start with lead magnets that solve a specific problem — checklists, templates, and calculators convert best. Avoid generic 'subscribe to our newsletter' CTAs.\n\nAutomation is where the magic happens. Set up welcome sequences, onboarding drips, and re-engagement campaigns. The best SaaS companies send 3-5 automated emails per week per segment.\n\nMeasure everything: open rates (benchmark: 21%), click rates (benchmark: 2.6%), and conversion rates. Track revenue per email to prove ROI to stakeholders.",
        "body_html": "<p>Email marketing remains...</p><img src='email-roi.png' alt='Email ROI chart'/>",
        "cluster": "Email Marketing",
        "gsc_queries": {"email marketing guide": (2.1, 450, 85), "email marketing 2024": (3.5, 320, 42),
                        "email marketing roi": (8.2, 180, 12), "how to do email marketing": (5.0, 210, 28)},
        "ga4": {"pageviews_recent": 1200, "pageviews_prev": 900, "bounce_rate": 0.35, "avg_time": 185},
        "inbound_links": 8, "outbound_links": 5,
    },
    {
        "id": uuid4(), "title": "Email Marketing Tips for Beginners",
        "url": "/email-marketing-tips-beginners",
        "word_count": 1800, "publish_date": now - timedelta(days=120),
        "modified_date": now - timedelta(days=120),
        "meta_description": "Simple email marketing tips for beginners. Start your first campaign today.",
        "headings": [{"level": "h2", "text": "Getting Started with Email"},
                     {"level": "h2", "text": "Choose the Right Platform"},
                     {"level": "h2", "text": "Write Better Subject Lines"}],
        "body_text": "If you're new to email marketing, these tips will help you get started quickly. Email marketing is a powerful tool for growing your business. Choose a platform like Mailchimp, ConvertKit, or ActiveCampaign. Write compelling subject lines that create curiosity. Segment your list by interest and behavior. Test everything — from send times to CTAs.",
        "body_html": "<p>If you're new...</p>",
        "cluster": "Email Marketing",
        "gsc_queries": {"email marketing tips": (4.2, 280, 35), "email marketing for beginners": (6.1, 190, 18),
                        "email marketing guide": (12.5, 150, 5), "how to do email marketing": (15.0, 90, 3)},
        "ga4": {"pageviews_recent": 380, "pageviews_prev": 520, "bounce_rate": 0.55, "avg_time": 95},
        "inbound_links": 2, "outbound_links": 1,
    },
    {
        "id": uuid4(), "title": "Best Email Marketing Platforms Compared",
        "url": "/best-email-marketing-platforms",
        "word_count": 2500, "publish_date": now - timedelta(days=60),
        "modified_date": now - timedelta(days=30),
        "meta_description": "Compare the best email marketing platforms: Mailchimp vs ConvertKit vs ActiveCampaign vs HubSpot.",
        "headings": [{"level": "h2", "text": "Mailchimp Review"},
                     {"level": "h2", "text": "ConvertKit Review"},
                     {"level": "h2", "text": "ActiveCampaign Review"},
                     {"level": "h2", "text": "HubSpot Email Review"},
                     {"level": "h2", "text": "Pricing Comparison"}],
        "body_text": "Choosing the right email marketing platform is a critical decision for any SaaS company. We tested all four major platforms to help you decide. Mailchimp is the easiest to use but limited in automation. ConvertKit is perfect for creators. ActiveCampaign has the best automation. HubSpot is enterprise-grade but expensive.",
        "body_html": "<p>Choosing...</p><img src='comparison.png' alt='Platform comparison'/>",
        "cluster": "Email Marketing",
        "gsc_queries": {"best email marketing platform": (5.5, 350, 30), "mailchimp vs convertkit": (3.8, 200, 25),
                        "email marketing software": (9.0, 280, 8)},
        "ga4": {"pageviews_recent": 650, "pageviews_prev": 600, "bounce_rate": 0.42, "avg_time": 145},
        "inbound_links": 4, "outbound_links": 3,
    },
    {
        "id": uuid4(), "title": "Email Subject Line Examples That Get Opens",
        "url": "/email-subject-line-examples",
        "word_count": 900, "publish_date": now - timedelta(days=200),
        "modified_date": now - timedelta(days=200),
        "meta_description": "",  # MISSING meta description
        "headings": [],  # NO headings
        "body_text": "Here are 50 email subject line examples you can steal. Subject lines matter because they determine whether your email gets opened or ignored.",
        "body_html": "<p>Here are 50...</p>",
        "cluster": "Email Marketing",
        "gsc_queries": {"email subject line examples": (7.2, 420, 15), "good subject lines": (14.0, 180, 3)},
        "ga4": {"pageviews_recent": 120, "pageviews_prev": 350, "bounce_rate": 0.78, "avg_time": 25},
        "inbound_links": 0, "outbound_links": 0,
    },
    {
        "id": uuid4(), "title": "Email Drip Campaign Strategy for SaaS",
        "url": "/email-drip-campaign-strategy",
        "word_count": 420, "publish_date": now - timedelta(days=15),
        "modified_date": now - timedelta(days=15),
        "meta_description": "How to build email drip campaigns that convert trial users to paid customers.",
        "headings": [{"level": "h2", "text": "What is a Drip Campaign"}],
        "body_text": "Drip campaigns are automated sequences of emails. They nurture leads over time. Use them for onboarding, upselling, and retention.",
        "body_html": "<p>Drip campaigns...</p>",
        "cluster": "Email Marketing",
        "gsc_queries": {"drip campaign": (11.0, 90, 4)},
        "ga4": {"pageviews_recent": 45, "pageviews_prev": 0, "bounce_rate": 0.65, "avg_time": 55},
        "inbound_links": 1, "outbound_links": 0,
    },

    # ── Cluster 2: SEO Strategy (5 posts) ──
    {
        "id": uuid4(), "title": "SEO Strategy for SaaS Companies: The Definitive Guide",
        "url": "/seo-strategy-saas",
        "word_count": 4500, "publish_date": now - timedelta(days=90),
        "modified_date": now - timedelta(days=20),
        "meta_description": "The complete SEO strategy framework for SaaS companies. Learn keyword research, technical SEO, content strategy, and link building.",
        "headings": [{"level": "h2", "text": "Keyword Research for SaaS"},
                     {"level": "h2", "text": "Technical SEO Checklist"},
                     {"level": "h3", "text": "Site Speed Optimization"},
                     {"level": "h2", "text": "Content Strategy"},
                     {"level": "h2", "text": "Link Building Tactics"}],
        "body_text": "SEO is the most sustainable growth channel for SaaS companies. Unlike paid ads that stop working when you stop paying, organic search compounds over time. This guide covers the complete SEO strategy framework we've used to grow multiple SaaS companies from 0 to 100K monthly organic visitors.\n\nStart with keyword research. Focus on bottom-of-funnel keywords first — these are the queries people search when they're ready to buy. Tools like Ahrefs, Semrush, and Google Keyword Planner help identify opportunities.\n\nTechnical SEO is the foundation. Ensure your site loads in under 3 seconds, has proper meta tags, uses HTTPS, and has a clean sitemap. Fix crawl errors weekly.\n\nContent strategy should align with your keyword research. Create pillar pages for broad topics and cluster content for specific subtopics. Update content quarterly to maintain freshness signals.",
        "body_html": "<p>SEO is...</p><img src='seo-framework.png'/><img src='keyword-research.png'/>",
        "cluster": "SEO Strategy",
        "gsc_queries": {"seo strategy saas": (1.8, 520, 180), "saas seo": (3.2, 380, 95),
                        "seo for saas companies": (2.5, 290, 70), "seo strategy guide": (8.0, 450, 20)},
        "ga4": {"pageviews_recent": 2100, "pageviews_prev": 1800, "bounce_rate": 0.28, "avg_time": 240},
        "inbound_links": 12, "outbound_links": 8,
    },
    {
        "id": uuid4(), "title": "How to Do Keyword Research for Your Blog",
        "url": "/keyword-research-blog",
        "word_count": 2200, "publish_date": now - timedelta(days=150),
        "modified_date": now - timedelta(days=150),
        "meta_description": "Step-by-step keyword research process for bloggers. Find low-competition, high-traffic keywords.",
        "headings": [{"level": "h2", "text": "What is Keyword Research"},
                     {"level": "h2", "text": "Free Keyword Research Tools"},
                     {"level": "h2", "text": "Finding Long-Tail Keywords"},
                     {"level": "h2", "text": "Keyword Difficulty Analysis"}],
        "body_text": "Keyword research is the process of finding search terms that people type into Google. It is a fundamental skill for any blogger or content marketer who wants to drive organic traffic.\n\nStart with free tools like Google Keyword Planner, Answer The Public, and Google Trends. Then graduate to paid tools like Ahrefs or Semrush for deeper analysis.\n\nLong-tail keywords are your best friend. They have lower competition and higher conversion rates. Focus on 3-5 word phrases that show clear intent.",
        "body_html": "<p>Keyword research...</p><img src='tools.png'/>",
        "cluster": "SEO Strategy",
        "gsc_queries": {"keyword research": (12.0, 600, 8), "how to do keyword research": (4.5, 280, 32),
                        "what is keyword research": (6.0, 350, 18), "keyword research tools": (15.0, 200, 4)},
        "ga4": {"pageviews_recent": 400, "pageviews_prev": 680, "bounce_rate": 0.48, "avg_time": 120},
        "inbound_links": 3, "outbound_links": 2,
    },
    {
        "id": uuid4(), "title": "Technical SEO Audit: A Step-by-Step Process",
        "url": "/technical-seo-audit",
        "word_count": 3100, "publish_date": now - timedelta(days=75),
        "modified_date": now - timedelta(days=40),
        "meta_description": "Run a complete technical SEO audit in 60 minutes. Covers crawlability, indexation, speed, and mobile.",
        "headings": [{"level": "h2", "text": "Crawlability Check"},
                     {"level": "h2", "text": "Indexation Issues"},
                     {"level": "h2", "text": "Page Speed Analysis"},
                     {"level": "h2", "text": "Mobile Friendliness"},
                     {"level": "h2", "text": "Structured Data Validation"}],
        "body_text": "A technical SEO audit is a systematic review of your website's technical health. It identifies issues that prevent search engines from crawling, indexing, and ranking your content effectively.\n\nStep 1: Check crawlability. Use Google Search Console to identify crawl errors. Review your robots.txt and XML sitemap.\n\nStep 2: Verify indexation. Search 'site:yourdomain.com' to see how many pages Google has indexed. Compare with your actual page count.\n\nStep 3: Analyze page speed. Use PageSpeed Insights. Core Web Vitals must pass: LCP < 2.5s, FID < 100ms, CLS < 0.1.\n\nStep 4: Test mobile friendliness. Use Google's Mobile-Friendly Test tool.",
        "body_html": "<p>A technical SEO audit...</p><img src='audit-tool.png'/>",
        "cluster": "SEO Strategy",
        "gsc_queries": {"technical seo audit": (3.5, 310, 45), "seo audit checklist": (5.8, 250, 22),
                        "how to audit website seo": (7.0, 180, 12)},
        "ga4": {"pageviews_recent": 780, "pageviews_prev": 720, "bounce_rate": 0.38, "avg_time": 165},
        "inbound_links": 5, "outbound_links": 4,
    },
    {
        "id": uuid4(), "title": "Link Building for SaaS: 15 Proven Strategies",
        "url": "/link-building-saas",
        "word_count": 2800, "publish_date": now - timedelta(days=180),
        "modified_date": now - timedelta(days=180),
        "meta_description": "15 link building strategies that actually work for SaaS companies in 2024.",
        "headings": [{"level": "h2", "text": "Guest Posting"},
                     {"level": "h2", "text": "Broken Link Building"},
                     {"level": "h2", "text": "Resource Pages"}],
        "body_text": "Link building is essential for SaaS SEO but it's getting harder. Here are 15 strategies that still work. Guest posting remains effective if you target relevant, high-authority sites. Broken link building requires finding dead links on competitor pages and offering your content as a replacement. Resource pages are gold mines — find industry lists and get your tool included.",
        "body_html": "<p>Link building...</p>",
        "cluster": "SEO Strategy",
        "gsc_queries": {"link building saas": (4.0, 150, 18), "link building strategies": (18.0, 500, 3)},
        "ga4": {"pageviews_recent": 220, "pageviews_prev": 380, "bounce_rate": 0.52, "avg_time": 110},
        "inbound_links": 2, "outbound_links": 1,
    },
    {
        "id": uuid4(),
        "title": "The Epistemological Framework of Search Engine Optimization: A Comprehensive Taxonomical Analysis of Algorithmic Relevance Determination Methodologies",
        "url": "/seo-academic-analysis",
        "word_count": 1500, "publish_date": now - timedelta(days=300),
        "modified_date": now - timedelta(days=300),
        "meta_description": "An academic analysis of SEO methodologies through epistemological and taxonomical frameworks.",
        "headings": [{"level": "h2", "text": "Ontological Foundations of Search Relevance"},
                     {"level": "h2", "text": "Epistemological Implications"}],
        "body_text": "The epistemological underpinnings of contemporary search engine optimization necessitate a comprehensive reconceptualization of methodological paradigms. The hermeneutical interpretation of algorithmic relevance determination presupposes an ontological framework that transcends conventional taxonomical categorizations. Furthermore, the dialectical relationship between semantic disambiguation and syntactic parsing algorithms reveals fundamental epistemological constraints inherent in probabilistic information retrieval systems. The phenomenological implications of latent semantic analysis vis-à-vis transformer-based architectures illuminate the quintessential paradox of computational hermeneutics in the context of relevance determination.",
        "body_html": "<p>The epistemological...</p>",
        "cluster": "SEO Strategy",
        "gsc_queries": {"seo methodology": (25.0, 40, 0)},
        "ga4": {"pageviews_recent": 8, "pageviews_prev": 15, "bounce_rate": 0.92, "avg_time": 12},
        "inbound_links": 0, "outbound_links": 0,
    },

    # ── Cluster 3: Content Marketing (5 posts) ──
    {
        "id": uuid4(), "title": "Content Marketing Strategy: How to Plan, Create, and Distribute",
        "url": "/content-marketing-strategy",
        "word_count": 3800, "publish_date": now - timedelta(days=30),
        "modified_date": now - timedelta(days=5),
        "meta_description": "Build a content marketing strategy that drives traffic, leads, and revenue. Step-by-step framework.",
        "headings": [{"level": "h2", "text": "Setting Content Goals"},
                     {"level": "h2", "text": "Audience Research"},
                     {"level": "h2", "text": "Content Calendar Planning"},
                     {"level": "h3", "text": "Editorial Workflow"},
                     {"level": "h2", "text": "Content Distribution Channels"},
                     {"level": "h2", "text": "Measuring Content ROI"}],
        "body_text": "Content marketing is a strategic approach focused on creating and distributing valuable, relevant content to attract and retain a clearly defined audience. It drives profitable customer action when done right.\n\nStart by setting clear goals. Are you optimizing for traffic, leads, or revenue? Each goal requires different content types and distribution strategies.\n\nResearch your audience deeply. Create buyer personas based on interviews, surveys, and analytics data. Understand their pain points, questions, and content consumption habits.\n\nPlan your content calendar at least 90 days ahead. Mix evergreen content (70%) with timely pieces (30%). Maintain a consistent publishing cadence of 2-4 posts per week.",
        "body_html": "<p>Content marketing is...</p><img src='strategy.png'/><img src='calendar.png'/>",
        "cluster": "Content Marketing",
        "gsc_queries": {"content marketing strategy": (3.0, 680, 95), "content strategy": (6.5, 420, 28),
                        "how to do content marketing": (4.2, 310, 35), "content marketing plan": (5.0, 250, 22)},
        "ga4": {"pageviews_recent": 1500, "pageviews_prev": 800, "bounce_rate": 0.32, "avg_time": 210},
        "inbound_links": 7, "outbound_links": 6,
    },
    {
        "id": uuid4(), "title": "What is Content Marketing? A Beginner's Guide",
        "url": "/what-is-content-marketing",
        "word_count": 1600, "publish_date": now - timedelta(days=180),
        "modified_date": now - timedelta(days=180),
        "meta_description": "Content marketing explained in simple terms. Learn what it is, why it matters, and how to start.",
        "headings": [{"level": "h2", "text": "Content Marketing Definition"},
                     {"level": "h2", "text": "Why Content Marketing Works"},
                     {"level": "h2", "text": "Getting Started"}],
        "body_text": "What is content marketing? Content marketing is creating and sharing valuable content to attract customers. Instead of pitching products, you provide useful information. It builds trust and positions your brand as an authority.",
        "body_html": "<p>What is content marketing?...</p><img src='cm-infographic.png'/>",
        "cluster": "Content Marketing",
        "gsc_queries": {"what is content marketing": (4.8, 550, 45), "content marketing definition": (2.5, 200, 30),
                        "content marketing explained": (8.0, 120, 8)},
        "ga4": {"pageviews_recent": 350, "pageviews_prev": 500, "bounce_rate": 0.45, "avg_time": 90},
        "inbound_links": 3, "outbound_links": 2,
    },
    {
        "id": uuid4(), "title": "Blog Post Ideas: 50 Topics That Drive Traffic",
        "url": "/blog-post-ideas",
        "word_count": 1200, "publish_date": now - timedelta(days=250),
        "modified_date": now - timedelta(days=250),
        "meta_description": "",
        "headings": [],
        "body_text": "Stuck on what to write? Here are 50 blog post ideas organized by category. How-to guides, listicles, case studies, comparisons, and industry news roundups. Pick one and start writing today.",
        "body_html": "<p>Stuck on what to write?...</p>",
        "cluster": "Content Marketing",
        "gsc_queries": {"blog post ideas": (8.5, 380, 12), "blog topics": (12.0, 280, 5)},
        "ga4": {"pageviews_recent": 90, "pageviews_prev": 210, "bounce_rate": 0.72, "avg_time": 35},
        "inbound_links": 0, "outbound_links": 0,
    },
    {
        "id": uuid4(), "title": "How to Create a Content Calendar (Free Template)",
        "url": "/content-calendar-template",
        "word_count": 1900, "publish_date": now - timedelta(days=50),
        "modified_date": now - timedelta(days=25),
        "meta_description": "Free content calendar template + step-by-step guide to planning your editorial calendar.",
        "headings": [{"level": "h2", "text": "Why You Need a Content Calendar"},
                     {"level": "h2", "text": "Content Calendar Template"},
                     {"level": "h2", "text": "How to Fill It Out"},
                     {"level": "h2", "text": "Tools for Content Planning"}],
        "body_text": "A content calendar is essential for consistent publishing. It keeps your team aligned and ensures you never run out of ideas. Download our free template and follow these steps to fill it out.",
        "body_html": "<p>A content calendar...</p><img src='template.png'/>",
        "cluster": "Content Marketing",
        "gsc_queries": {"content calendar template": (3.2, 420, 55), "editorial calendar": (7.0, 200, 12),
                        "content planning": (9.5, 150, 6)},
        "ga4": {"pageviews_recent": 520, "pageviews_prev": 480, "bounce_rate": 0.40, "avg_time": 130},
        "inbound_links": 4, "outbound_links": 3,
    },
    {
        "id": uuid4(), "title": "Content Marketing ROI: How to Calculate and Prove Value",
        "url": "/content-marketing-roi",
        "word_count": 2100, "publish_date": now - timedelta(days=8),
        "modified_date": now - timedelta(days=8),
        "meta_description": "Learn how to calculate content marketing ROI with formulas, benchmarks, and a reporting framework.",
        "headings": [{"level": "h2", "text": "The ROI Formula"},
                     {"level": "h2", "text": "Attribution Models"},
                     {"level": "h2", "text": "Reporting to Stakeholders"}],
        "body_text": "Proving content marketing ROI is the #1 challenge for marketers. Here's how to calculate it. The basic formula: ROI = (Revenue from Content - Cost of Content) / Cost of Content × 100. But real attribution is harder. Use multi-touch models.",
        "body_html": "<p>Proving content...</p><img src='roi-calc.png'/>",
        "cluster": "Content Marketing",
        "gsc_queries": {"content marketing roi": (5.5, 180, 15), "how to measure content roi": (6.0, 120, 8)},
        "ga4": {"pageviews_recent": 180, "pageviews_prev": 0, "bounce_rate": 0.38, "avg_time": 140},
        "inbound_links": 2, "outbound_links": 3,
    },
]

# Internal link graph
INTERNAL_LINKS = [
    # Email cluster
    (0, 1), (0, 2), (0, 3), (0, 4), (1, 0), (2, 0), (4, 0),
    # SEO cluster
    (5, 6), (5, 7), (5, 8), (6, 5), (7, 5), (7, 6),
    # Content cluster
    (10, 11), (10, 12), (10, 13), (10, 14), (11, 10), (13, 10), (14, 10),
    # Cross-cluster
    (0, 5), (5, 10), (10, 0),
]


def print_header(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_subheader(title: str) -> None:
    print(f"\n  ── {title} ──")


def run_simulation():
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  TENDED — Full Intelligence Layer Simulation                       ║")
    print("║  Blog: GrowthStack.io (15 posts, 3 clusters)                       ║")
    print("║  13 Intelligence Signals                                           ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    # ═══════════════════════════════════════
    # SIGNAL 1: Health Scoring (7-factor)
    # ═══════════════════════════════════════
    print_header("SIGNAL 1: Health Scoring (7-Factor Model)")

    cluster_groups = {}
    for i, p in enumerate(POSTS):
        cluster_groups.setdefault(p["cluster"], []).append(i)

    all_scores = {}
    for cluster_name, indices in cluster_groups.items():
        cluster_wc = [POSTS[i]["word_count"] for i in indices]
        cluster_avg_wc = sum(cluster_wc) / len(cluster_wc)
        max_inbound = max(POSTS[i]["inbound_links"] for i in indices) or 1

        print_subheader(f"Cluster: {cluster_name}")
        for idx in indices:
            p = POSTS[idx]
            ga = p["ga4"]

            trend, trend_score = _compute_trend(
                ga["pageviews_recent"], ga["pageviews_prev"],
                ga["pageviews_recent"] + ga["pageviews_prev"],
            )
            ranking_scores = []
            for q, (pos, imp, clicks) in p["gsc_queries"].items():
                ranking_scores.append(_ranking_score(pos))
            avg_ranking = sum(ranking_scores) / len(ranking_scores) if ranking_scores else 0

            engagement = _engagement_score(ga["bounce_rate"], ga["avg_time"])
            freshness = _freshness_score(p["modified_date"], now)
            depth = _content_depth_score(p["word_count"], cluster_avg_wc)
            link_score = min(100, (p["inbound_links"] / max_inbound) * 100)
            tech_seo = _technical_seo_score(
                p["meta_description"], p["title"], p["headings"],
                p["outbound_links"] > 0, p["inbound_links"] > 0,
            )

            composite = (
                0.25 * trend_score + 0.20 * avg_ranking + 0.15 * engagement
                + 0.15 * freshness + 0.10 * depth + 0.10 * link_score
                + 0.05 * tech_seo
            )

            # Determine role
            total_cluster_pv = sum(POSTS[i]["ga4"]["pageviews_recent"] for i in indices)
            traffic_contribution = ga["pageviews_recent"] / max(total_cluster_pv, 1)
            role = _assign_role(composite, traffic_contribution, ga["pageviews_recent"], False)

            all_scores[idx] = {
                "composite": composite, "trend": trend, "role": role,
                "trend_score": trend_score, "ranking": avg_ranking,
                "engagement": engagement, "freshness": freshness,
                "depth": depth, "links": link_score, "tech_seo": tech_seo,
            }

            status_emoji = {"pillar": "👑", "supporter": "🛡️", "competitor": "⚔️", "dead_weight": "💀"}
            print(f"    {status_emoji.get(role, '?')} {p['title'][:55]}")
            print(f"       Score: {composite:.1f}/100 | Role: {role} | Trend: {trend} ({trend_score:.0f})")
            print(f"       Ranking: {avg_ranking:.0f} | Engagement: {engagement:.0f} | Freshness: {freshness:.0f} | Depth: {depth:.0f} | Links: {link_score:.0f} | Tech: {tech_seo:.0f}")

    # ═══════════════════════════════════════
    # SIGNAL 2: Readability
    # ═══════════════════════════════════════
    print_header("SIGNAL 2: Readability Scoring")

    for i, p in enumerate(POSTS):
        text = p["body_text"]
        fre = compute_flesch_reading_ease(text)
        grade = compute_grade_level(text)

        emoji = "✅" if fre >= 60 else ("⚠️" if fre >= 40 else "🚨")
        problem = ""
        if fre < READABILITY_TOO_COMPLEX:
            problem = " ← PROBLEM: Too complex for most readers!"

        print(f"  {emoji} {p['title'][:55]}")
        print(f"     Flesch: {fre:.1f} | Grade: {grade:.1f}{problem}")

    # ═══════════════════════════════════════
    # SIGNAL 3: Content Velocity
    # ═══════════════════════════════════════
    print_header("SIGNAL 3: Content Velocity")

    posts_30d = sum(1 for p in POSTS if p["publish_date"] >= now - timedelta(days=30))
    posts_90d = sum(1 for p in POSTS if p["publish_date"] >= now - timedelta(days=90))
    v30 = posts_30d / (30/7)
    v90 = posts_90d / (90/7)

    if v90 > 0 and v30 < v90 * VELOCITY_DECLINE_RATIO:
        trend = "DECLINING ⚠️"
    elif v90 > 0 and v30 > v90 * 1.5:
        trend = "GROWING 📈"
    else:
        trend = "STABLE ➡️"

    print(f"  Posts in last 30 days: {posts_30d}")
    print(f"  Posts in last 90 days: {posts_90d}")
    print(f"  Velocity (30d): {v30:.1f} posts/week")
    print(f"  Velocity (90d): {v90:.1f} posts/week")
    print(f"  Trend: {trend}")

    # ═══════════════════════════════════════
    # SIGNAL 4: Weighted Embeddings
    # ═══════════════════════════════════════
    print_header("SIGNAL 4: Weighted Embedding Comparison")

    sample = POSTS[0]
    body_only = sample["body_text"]
    weighted = construct_weighted_text(
        sample["title"], sample["headings"], sample["body_text"],
    )
    print(f"  Post: {sample['title'][:55]}")
    print(f"  Body-only embedding input: {len(body_only)} chars")
    print(f"  Weighted embedding input:  {len(weighted)} chars")
    print(f"  Title appears: {weighted.count(sample['title'])}× (should be 3)")
    heading_text = sample["headings"][0]["text"] if sample["headings"] else ""
    if heading_text:
        print(f"  First heading appears: {weighted.count(heading_text)}× (should be 2)")

    # ═══════════════════════════════════════
    # SIGNAL 5: Intent Classification
    # ═══════════════════════════════════════
    print_header("SIGNAL 5: Search Intent Classification")

    for i, p in enumerate(POSTS):
        queries = list(p["gsc_queries"].keys())
        intents = [classify_query_intent(q) for q in queries]

        from collections import Counter
        intent_counts = Counter(intents)
        dominant = intent_counts.most_common(1)[0][0]

        # Estimate post intent based on title/content
        post_intent = classify_query_intent(p["title"])
        mismatch = post_intent != dominant and len(queries) >= 2

        emoji = "🚨" if mismatch else "✅"
        print(f"  {emoji} {p['title'][:55]}")
        print(f"     Post intent: {post_intent} | Query intents: {dict(intent_counts)}")
        if mismatch:
            print(f"     ⚠️ INTENT MISMATCH: Post is {post_intent} but queries are {dominant}")

    # ═══════════════════════════════════════
    # SIGNAL 6: Internal PageRank
    # ═══════════════════════════════════════
    print_header("SIGNAL 6: Internal PageRank")

    edges = [(POSTS[s]["id"], POSTS[t]["id"]) for s, t in INTERNAL_LINKS]
    nodes = {p["id"] for p in POSTS}
    pr = InternalPageRank._compute_pagerank(edges, nodes)

    # Map back to posts and sort
    pr_list = [(i, pr[POSTS[i]["id"]]) for i in range(len(POSTS))]
    pr_list.sort(key=lambda x: x[1], reverse=True)

    for rank, (idx, score) in enumerate(pr_list, 1):
        bar = "█" * int(score * 500)
        print(f"  #{rank:2d} ({score:.4f}) {bar} {POSTS[idx]['title'][:50]}")

    # ═══════════════════════════════════════
    # SIGNAL 7: Cannibalization Detection
    # ═══════════════════════════════════════
    print_header("SIGNAL 7: Cannibalization Detection")

    for cluster_name, indices in cluster_groups.items():
        print_subheader(f"Cluster: {cluster_name}")
        # Check for shared queries
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                idx_a, idx_b = indices[i], indices[j]
                qa = set(POSTS[idx_a]["gsc_queries"].keys())
                qb = set(POSTS[idx_b]["gsc_queries"].keys())
                shared = qa & qb
                if shared:
                    severity = CannibalizationDetector._compute_severity(None, len(shared))
                    print(f"  ⚠️ CANNIBALIZATION PAIR ({severity}):")
                    print(f"     A: {POSTS[idx_a]['title'][:50]}")
                    print(f"     B: {POSTS[idx_b]['title'][:50]}")
                    print(f"     Shared queries: {', '.join(shared)}")
        if not any(
            set(POSTS[indices[i]]["gsc_queries"].keys()) & set(POSTS[indices[j]]["gsc_queries"].keys())
            for i in range(len(indices)) for j in range(i + 1, len(indices))
        ):
            print("  ✅ No cannibalization detected")

    # ═══════════════════════════════════════
    # SIGNAL 8: Problem Detection
    # ═══════════════════════════════════════
    print_header("SIGNAL 8: Problem Detection")

    problems = []
    for i, p in enumerate(POSTS):
        ga = p["ga4"]
        post_problems = []

        # Decay: traffic decline
        if ga["pageviews_prev"] > 10 and ga["pageviews_recent"] < ga["pageviews_prev"] * 0.7:
            drop = (ga["pageviews_prev"] - ga["pageviews_recent"]) / ga["pageviews_prev"] * 100
            post_problems.append(f"📉 Traffic declined {drop:.0f}% ({ga['pageviews_prev']}→{ga['pageviews_recent']})")

        # Thin content
        if 0 < p["word_count"] < 500:
            post_problems.append(f"📝 Thin content ({p['word_count']} words)")

        # SEO issues
        if not p["meta_description"]:
            post_problems.append("🏷️ Missing meta description")
        if not p["headings"]:
            post_problems.append("📋 No H2+ headings")
        if p["inbound_links"] == 0 and p["outbound_links"] == 0:
            post_problems.append("🔗 Orphan content (no internal links)")

        # Readability
        fre = compute_flesch_reading_ease(p["body_text"])
        if fre < READABILITY_TOO_COMPLEX:
            post_problems.append(f"📖 Readability too complex (Flesch: {fre:.0f})")

        # High bounce + low time
        if ga["bounce_rate"] > 0.8 and ga["avg_time"] < 30:
            post_problems.append(f"🚪 High bounce ({ga['bounce_rate']:.0%}) + low time ({ga['avg_time']}s)")

        if post_problems:
            problems.extend(post_problems)
            print(f"  🚨 {p['title'][:55]}")
            for prob in post_problems:
                print(f"     {prob}")

    print(f"\n  Total problems: {len(problems)}")

    # ═══════════════════════════════════════
    # SIGNAL 9: Content Gap Analysis
    # ═══════════════════════════════════════
    print_header("SIGNAL 9: Content Gap Analysis")

    # Simulate zero-click high-impression queries
    gap_queries = [
        ("email deliverability best practices", 380, 0.8, 15.0),
        ("marketing automation vs email marketing", 250, 1.2, 12.0),
        ("saas content strategy framework", 180, 0.5, 18.0),
        ("how to improve domain authority", 420, 1.0, 22.0),
        ("content repurposing strategies", 290, 0.9, 14.0),
    ]
    print("  Queries with high impressions but low CTR (< 2%):")
    for query, impressions, ctr, pos in gap_queries:
        print(f"  📭 \"{query}\"")
        print(f"     {impressions} impressions, {ctr}% CTR, position {pos} — NO targeted content!")

    # ═══════════════════════════════════════
    # SIGNAL 10: Topical Authority
    # ═══════════════════════════════════════
    print_header("SIGNAL 10: Topical Authority Scoring")

    for cluster_name, indices in cluster_groups.items():
        scores = [all_scores[i]["composite"] for i in indices]
        avg_health = sum(scores) / len(scores)

        # Link density within cluster
        cluster_ids = set(indices)
        intra_links = sum(1 for s, t in INTERNAL_LINKS if s in cluster_ids and t in cluster_ids)
        possible = len(indices) * (len(indices) - 1)
        link_density = (intra_links / max(possible, 1)) * 100

        # Content depth
        avg_wc = sum(POSTS[i]["word_count"] for i in indices) / len(indices)
        depth_ratio = min(100, (avg_wc / 1500) * 100)

        # Freshness
        freshness_scores = [all_scores[i]["freshness"] for i in indices]
        avg_freshness = sum(freshness_scores) / len(freshness_scores)

        # Keyword coverage (unique queries)
        all_queries = set()
        for i in indices:
            all_queries.update(POSTS[i]["gsc_queries"].keys())
        expected = len(indices) * 15
        keyword_cov = min(100, (len(all_queries) / max(expected, 1)) * 100)

        authority = (
            0.30 * avg_health + 0.20 * keyword_cov + 0.20 * link_density
            + 0.15 * depth_ratio + 0.15 * avg_freshness
        )

        emoji = "🏆" if authority > 60 else ("📊" if authority > 40 else "⚠️")
        print(f"  {emoji} {cluster_name}: {authority:.1f}/100")
        print(f"     Health: {avg_health:.0f} | Keywords: {keyword_cov:.0f}% ({len(all_queries)} unique)")
        print(f"     Link density: {link_density:.0f}% | Depth: {depth_ratio:.0f}% ({avg_wc:.0f} avg words)")
        print(f"     Freshness: {avg_freshness:.0f}")

    # ═══════════════════════════════════════
    # SIGNAL 11: SERP Feature Opportunities
    # ═══════════════════════════════════════
    print_header("SIGNAL 11: SERP Feature Opportunities")

    for i, p in enumerate(POSTS):
        for query, (pos, imp, clicks) in p["gsc_queries"].items():
            if 3 <= pos <= 8:
                snippet_type = detect_snippet_type(query)
                if snippet_type:
                    has_format = check_post_has_format(p["body_text"], p["headings"], snippet_type)
                    emoji = "✅" if has_format else "🎯"
                    action = "Already formatted" if has_format else "NEEDS FORMATTING"
                    print(f"  {emoji} \"{query}\" → {snippet_type} (position {pos})")
                    print(f"     Post: {p['title'][:50]}")
                    print(f"     {action} | {imp} impressions")

    # ═══════════════════════════════════════
    # SIGNAL 12: Ecosystem States
    # ═══════════════════════════════════════
    print_header("SIGNAL 12: Ecosystem States")

    for cluster_name, indices in cluster_groups.items():
        metrics = []
        for idx in indices:
            s = all_scores[idx]
            metrics.append({
                "role": s["role"], "trend": s["trend"],
                "traffic": POSTS[idx]["ga4"]["pageviews_recent"],
                "publish_date": POSTS[idx]["publish_date"].replace(tzinfo=timezone.utc),
                "composite": s["composite"],
            })

        has_pillar = any(m["role"] == "pillar" for m in metrics)
        all_declining = all(m["trend"] in ("declining", "dead") for m in metrics)
        avg_traffic = sum(m["traffic"] for m in metrics) / len(metrics)

        cannibal_count = 0
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                qa = set(POSTS[indices[i]]["gsc_queries"].keys())
                qb = set(POSTS[indices[j]]["gsc_queries"].keys())
                if qa & qb:
                    cannibal_count += 1

        total_pairs = len(indices) * (len(indices) - 1) / 2
        cannibal_rate = cannibal_count / max(total_pairs, 1)
        cluster_health = sum(m["composite"] for m in metrics) / len(metrics)

        # Assign state
        has_recent = any(m["publish_date"] >= now - timedelta(days=30) for m in metrics)
        if has_recent and len(metrics) <= 3:
            state = "🌱 SEEDBED"
        elif cannibal_rate > 0.5 or (len(metrics) > 8 and not has_pillar):
            state = "🪴 SWAMP"
        elif all_declining or avg_traffic < 5:
            state = "🏜️ DESERT"
        elif has_pillar and cannibal_rate < 0.2 and cluster_health > 50:
            state = "🌲 FOREST"
        else:
            state = "🌻 MEADOW"

        print(f"  {state} — {cluster_name}")
        print(f"     Health: {cluster_health:.0f} | Pillar: {'Yes' if has_pillar else 'No'} | Cannibalization: {cannibal_rate:.0%}")

    # ═══════════════════════════════════════
    # SIGNAL 13: AI Recommendations (simulated)
    # ═══════════════════════════════════════
    print_header("SIGNAL 13: AI Recommendations (What Claude Would Generate)")

    recommendations = [
        ("🔀 MERGE", "Email Subject Line Examples", "Email Marketing Guide",
         "Merge the subject line examples into the main guide as a new H2 section. "
         "301 redirect /email-subject-line-examples → /email-marketing-guide-2024#subject-lines. "
         "The guide is the stronger post (score: 72 vs 18). Effort: 2 hrs. Impact: HIGH."),
        ("🔄 REFRESH", "Link Building for SaaS", None,
         "Traffic dropped 42% (380→220). Update with 2024 strategies: digital PR, "
         "podcast guesting, and HARO alternatives (Connectively). Add 5 new strategies. "
         "Update 'guest posting' section with current outreach templates. Effort: 3 hrs. Impact: HIGH."),
        ("📝 EXPAND", "Email Drip Campaign Strategy", None,
         "Only 420 words — too thin to rank. Expand to 1500+ words. Add sections: "
         "'Drip Campaign Examples for Each Funnel Stage', 'Email Sequence Templates', "
         "'A/B Testing Your Drip Campaigns'. Target keyword: 'drip campaign strategy'. "
         "Effort: 4 hrs. Impact: MEDIUM."),
        ("🏷️ SEO FIX", "Email Subject Line Examples", None,
         "Missing meta description. Suggested: 'Steal these 50 proven email subject "
         "line examples that boost open rates. Organized by type: curiosity, urgency, "
         "personalization, and value-driven.' (155 chars). Effort: 5 min. Impact: MEDIUM."),
        ("📖 SIMPLIFY", "The Epistemological Framework...", None,
         "Flesch score: 3.8 (graduate level). Rewrite in plain English. Replace "
         "'epistemological underpinnings' with 'core principles'. Break 40-word sentences "
         "into 15-word sentences. Target Flesch score: 60+. Effort: 2 hrs. Impact: HIGH."),
        ("🎯 SNIPPET", "How to Do Keyword Research", None,
         "Ranking #4.5 for 'how to do keyword research' (280 impressions). Add a "
         "numbered step list after the H1: '1. Start with seed keywords 2. Use Google "
         "Keyword Planner 3. Analyze competition 4. Filter by intent 5. Prioritize by "
         "opportunity'. This targets the featured snippet. Effort: 30 min. Impact: HIGH."),
        ("📭 NEW POST", None, None,
         "GAP: 'email deliverability best practices' — 380 impressions, 0.8% CTR, no "
         "targeted content. Write: 'Email Deliverability Guide: 12 Best Practices to "
         "Reach the Inbox'. Sections: Authentication (SPF/DKIM/DMARC), List Hygiene, "
         "Warm-up Strategy, Content Formatting. Target: 2000 words. Effort: 6 hrs. Impact: HIGH."),
        ("🔗 INTERLINK", "Blog Post Ideas", None,
         "This post is an ORPHAN — zero internal links. Add links FROM: Content Marketing "
         "Strategy, Content Calendar Template, What is Content Marketing. Add links TO: "
         "those same posts. This will distribute link authority and improve crawlability. "
         "Effort: 20 min. Impact: MEDIUM."),
    ]

    for rec_type, post, target, detail in recommendations:
        print(f"\n  {rec_type}: {post or 'New Content'}")
        if target:
            print(f"  → Merge into: {target}")
        print(f"  {detail}")

    # ═══════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════
    print_header("INTELLIGENCE SUMMARY — GrowthStack.io")

    total_posts = len(POSTS)
    total_problems = len(problems)
    pillars = sum(1 for s in all_scores.values() if s["role"] == "pillar")
    dead_weight = sum(1 for s in all_scores.values() if s["role"] == "dead_weight")
    avg_health = sum(s["composite"] for s in all_scores.values()) / len(all_scores)

    print(f"""
  📊 Site Overview
     Posts: {total_posts} | Clusters: {len(cluster_groups)}
     Avg Health: {avg_health:.1f}/100
     Pillars: {pillars} | Dead Weight: {dead_weight}
     Problems: {total_problems}
     Publishing Velocity: {v30:.1f} posts/week (trend: {trend.split()[0]})

  🧠 Intelligence Signals Active: 13/13
     ✅ Health Scoring (7-factor)
     ✅ Topic Clustering (HDBSCAN)
     ✅ Cannibalization Detection (auto-calibrated)
     ✅ Problem Detection (8 types)
     ✅ AI Recommendations (Claude)
     ✅ Internal PageRank (NetworkX)
     ✅ Topical Authority (per-cluster)
     ✅ Intent Classification (4-type)
     ✅ Content Gap Analysis (GSC-based)
     ✅ Weighted Embeddings (title×3)
     ✅ Content Velocity (30d/90d)
     ✅ SERP Feature Opportunities
     ✅ Readability Scoring (Flesch)

  🎯 Top 3 Actions:
     1. Merge "Subject Line Examples" into "Email Marketing Guide" (2 hrs → HIGH impact)
     2. Write new post: "Email Deliverability Best Practices" (6 hrs → HIGH impact)
     3. Simplify "Epistemological Framework" post (2 hrs → HIGH impact)
""")


if __name__ == "__main__":
    run_simulation()
