"""AI Citability Scoring — 2026 SEO readiness analysis.

Scores each post on 4 dimensions:
1. AI Citability Score (0-100): how likely an AI will cite/quote this post
2. E-E-A-T Score (0-100): Experience, Expertise, Authoritativeness, Trustworthiness signals
3. Schema Score (0-100): structured data completeness
4. Extraction Score (0-100): content structure optimised for AI extraction

All signals derived from already-crawled body_html + body_text. Zero new API calls.
"""
import json
import logging
import re
from uuid import UUID

import asyncpg
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Signal pattern constants ─────────────────────────────────────────────────

# First-person experience markers
FIRST_PERSON_PATTERNS = re.compile(
    r"\b(in our testing|when we (implemented|tested|tried|built|ran)|"
    r"we found|we discovered|in my experience|i tested|i found|"
    r"our (data|results|analysis|research|study|tests) (show|reveal|found|indicate)|"
    r"based on our|in practice|in real(-| )world|our team|we've been|"
    r"when i|after i|i've (been|used|tested|tried))\b",
    re.IGNORECASE,
)

# Statistics / original data markers
STATS_PATTERNS = re.compile(
    r"(\d+[\.,]?\d*\s*%|\d{4,}[\.,]?\d*\s*(users|companies|brands|sites|searches|queries|"
    r"customers|people|respondents|participants)|"
    r"\d+\s*(out of|in)\s*\d+|"
    r"(according to our|in our survey|our study|we surveyed|we analyzed|"
    r"we collected|our data|proprietary data))",
    re.IGNORECASE,
)

# Definition paragraph pattern — "[Topic] is/are/refers to [a/an/the/when/how]..."
# Requires article/determiner after verb to avoid matching declarative sentences like
# "Brian is excited" or "The problem is complex". Only matches actual definitions like
# "Content marketing is a strategy for..." or "SEO refers to the practice of..."
DEFINITION_PATTERNS = re.compile(
    r"^[A-Z][A-Za-z\s\-]{3,50}\b(is|are|refers to|means|can be defined as|describes)\s+"
    r"(?:a|an|the|when|how|any|one|not|essentially|basically|simply|generally|broadly)",
    re.MULTILINE,
)

# Citation / authority signals in body text
CITATION_PATTERNS = re.compile(
    r"(according to|as reported by|cited by|published by|per |source:|"
    r"from a (study|report|survey|research) by|data from|"
    r"\.gov|\.edu|journal|research|university|institute)",
    re.IGNORECASE,
)

# Schema types that signal AI-readiness
HIGH_VALUE_SCHEMA = {"Article", "NewsArticle", "BlogPosting", "FAQPage",
                     "HowTo", "TechArticle", "Dataset", "Review"}
BASIC_SCHEMA = {"Organization", "WebSite", "BreadcrumbList", "WebPage"}

# Author credential markers in bio text
AUTHOR_CREDENTIAL_PATTERNS = re.compile(
    r"\b(CEO|CTO|CMO|VP|director|manager|founder|co-founder|editor|journalist|"
    r"author|consultant|analyst|engineer|developer|researcher|scientist|professor|"
    r"PhD|MSc|MBA|years of experience|years experience|previously at|worked at|"
    r"former|ex-|advisor|expert|specialist|head of)\b",
    re.IGNORECASE,
)


def _parse_html(body_html: str) -> BeautifulSoup:
    return BeautifulSoup(body_html or "", "lxml")


# ── 1. AI Citability Score ────────────────────────────────────────────────────

def compute_citability_score(body_text: str, body_html: str, *, soup: BeautifulSoup | None = None) -> tuple[float, dict]:
    """0-100 score: how likely an AI will cite this content.

    Total possible points: ~135. Capped at 100 via min(sum, 100).
    This is intentional — posts can max out without hitting every signal,
    and different content types achieve 100 through different signal combinations.

    Signals:
    - Data tables (20 pts)
    - Numbered/ordered lists (15 pts)
    - First-person experience language (20 pts)
    - Original statistics/data (20 pts)
    - Definition paragraphs (10 pts)
    - Entity density (10 pts — approximate)
    - Credible external citations (5 pts)
    """
    if soup is None:
        soup = _parse_html(body_html)
    text = body_text or ""
    signals: dict = {}
    score = 0.0

    # Data tables
    tables = soup.find_all("table")
    has_tables = len(tables) >= 1
    signals["data_tables"] = len(tables)
    if has_tables:
        score += 20

    # Ordered lists (numbered sequences)
    ol_tags = soup.find_all("ol")
    ol_items = sum(len(ol.find_all("li")) for ol in ol_tags)
    signals["numbered_list_items"] = ol_items
    if ol_items >= 3:
        score += 15
    elif ol_items >= 1:
        score += 7

    # First-person experience
    fp_matches = len(FIRST_PERSON_PATTERNS.findall(text))
    signals["first_person_markers"] = fp_matches
    if fp_matches >= 3:
        score += 20
    elif fp_matches >= 1:
        score += 10

    # Original statistics
    stats_matches = len(STATS_PATTERNS.findall(text))
    signals["stats_mentions"] = stats_matches
    if stats_matches >= 3:
        score += 20
    elif stats_matches >= 1:
        score += 10

    # Definition paragraphs
    def_matches = len(DEFINITION_PATTERNS.findall(text))
    signals["definition_paragraphs"] = def_matches
    if def_matches >= 2:
        score += 10
    elif def_matches >= 1:
        score += 5

    # Entity density — count capitalized multi-word proper nouns / named entities
    # Approximate: count Title Case word sequences (2+ words)
    entity_pattern = re.compile(r"(?:[A-Z][a-z]+\s){1,}[A-Z][a-z]+")
    entities = entity_pattern.findall(text)
    words = len(text.split())
    entity_density = (len(entities) / max(words, 1)) * 1000  # per 1000 words
    signals["entity_density_per_1k"] = round(entity_density, 1)
    if entity_density >= 15:
        score += 10
    elif entity_density >= 8:
        score += 5

    # External credible citations
    citation_matches = len(CITATION_PATTERNS.findall(text))
    signals["citation_markers"] = citation_matches
    if citation_matches >= 2:
        score += 5

    # ── GEO-1 additions ──

    # Question-format H2/H3 headers (AI systems match prompts to question headers)
    if body_html:
        q_soup = _parse_html(body_html)
        h_tags = q_soup.find_all(["h2", "h3"])
        question_headers = sum(
            1 for h in h_tags
            if re.match(r"^(what|how|why|when|where|which|who|can|does|is|are|should|will)\s", h.get_text(strip=True), re.I)
        )
        total_headers = len(h_tags)
        question_ratio = question_headers / max(total_headers, 1)
        signals["question_headers"] = question_headers
        signals["total_headers"] = total_headers
        signals["question_header_ratio"] = round(question_ratio, 2)
        if question_ratio >= 0.3:
            score += 15
        elif question_ratio >= 0.15:
            score += 7

    # Data density — specific numbers/stats per 200 words
    data_points = len(re.findall(r"\d+[\.,]?\d*\s*%|\$\d+|\d{2,}[\.,]\d+|\d+\s*(million|billion|thousand|users|customers|companies)", text, re.I))
    data_density = (data_points / max(words, 1)) * 200  # per 200 words
    signals["data_points"] = data_points
    signals["data_density_per_200w"] = round(data_density, 2)
    if data_density >= 1.0:
        score += 10
    elif data_density >= 0.5:
        score += 5

    # Answer-first structure — first 200 words contain a direct answer
    first_200 = " ".join(text.split()[:200])
    has_answer_first = bool(
        re.search(r"\b(is|are|means|refers to|the (best|most|key|main)|you (can|should|need)|here's|here is)\b", first_200, re.I)
        and (re.search(r"\d", first_200) or re.search(r"\b(is|are|means|refers to|can be defined as)\b", first_200, re.I))
    )
    signals["answer_first_200w"] = has_answer_first
    if has_answer_first:
        score += 10

    signals["citability_score"] = round(min(score, 100))
    return round(min(score, 100)), signals


# ── 2. E-E-A-T Score ─────────────────────────────────────────────────────────

def compute_eeat_score(
    body_html: str,
    crawl_eeat: dict | None = None,
    headings: list[dict] | None = None,
    word_count: int = 0,
    site_median_words: int = 0,
    publish_date: "datetime | None" = None,
    modified_date: "datetime | None" = None,
    *,
    soup: BeautifulSoup | None = None,
) -> tuple[float, dict]:
    """0-100 E-E-A-T score — visible trust signals only.

    Measures what a human reader would perceive as trustworthy. Schema/structured
    data signals belong in the Schema dimension, not here.

    Calibrated across 4 iterations against Copyblogger (145 posts) and
    Backlinko (149 posts). Target: 30-90 range across a typical content
    marketing site, with post-specific signals creating meaningful variance.

    Site-wide signals (35 pts max):
    - Author byline present (15 pts)
    - Author bio present (10 pts)
    - Contact/About page link (10 pts)

    Post-specific signals (65 pts max):
    - Author credentials in bio (10 pts)
    - Date freshness (0/5/10/15 pts — graduated by recency)
    - Post-level outbound links (0/5/10/15 pts — graduated by count)
    - Post word count above site median (10 pts)
    - Post has 3+ H2 sections (15 pts)

    Args:
        body_html: Article-area HTML (main content only)
        crawl_eeat: Optional pre-extracted E-E-A-T metadata from full page HTML.
                    Used for site-wide signals (author name, contact link, date fallback).
        headings: Post headings list [{"level": "h2", "text": "..."}]
        word_count: Word count of this post
        site_median_words: Median word count across all posts in the site
        publish_date: Post publish date (for freshness scoring)
        modified_date: Post modified date (for freshness scoring, takes priority)
    """
    if soup is None:
        soup = _parse_html(body_html)
    ce = crawl_eeat or {}  # crawl-extracted E-E-A-T metadata
    signals: dict = {}
    score = 0.0

    # ── Author byline (15 pts — site-wide) ──────────────────────────────────
    # Detection ordered from most reliable to least.
    author_found = False
    author_name = None

    if ce.get("author_name"):
        author_found = True
        author_name = ce["author_name"]
    else:
        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author and meta_author.get("content"):
            author_found = True
            author_name = meta_author["content"].strip()[:60]

    if not author_found:
        byline_selectors = [
            {"class": re.compile(r"post-author|byline|entry-author", re.I)},
            {"rel": "author"},
        ]
        for sel in byline_selectors:
            tag = soup.find(True, sel)
            if tag:
                author_a = tag.find("a", href=re.compile(r"/authors?/", re.I))
                if author_a:
                    author_found = True
                    author_name = author_a.get_text(strip=True)[:60]
                    break
                name_el = tag.find("a") or tag.find("span") or tag.find("strong")
                if name_el:
                    author_found = True
                    author_name = name_el.get_text(strip=True)[:60]
                    break

    if not author_found:
        author_link = soup.find("a", href=re.compile(r"/authors?/[^/]+", re.I))
        if author_link and author_link.get_text(strip=True):
            author_found = True
            author_name = author_link.get_text(strip=True)[:60]

    if not author_found:
        generic_selectors = [
            {"itemprop": "author"},
            {"class": re.compile(r"author", re.I)},
        ]
        for sel in generic_selectors:
            tag = soup.find(True, sel)
            if tag:
                author_found = True
                author_a = tag.find("a", href=re.compile(r"/authors?/", re.I))
                if author_a:
                    author_name = author_a.get_text(strip=True)[:60]
                else:
                    # Try direct text first, then any nested <a>, then full tag text
                    direct_text = tag.find(string=True, recursive=False)
                    if direct_text and direct_text.strip():
                        author_name = direct_text.strip()[:60]
                    elif tag.find("a"):
                        author_name = tag.find("a").get_text(strip=True)[:60] or None
                    else:
                        # Last resort: all text in the element
                        full_text = tag.get_text(strip=True)
                        author_name = full_text[:60] if full_text else None
                break

    if not author_found:
        body_text_snippet = soup.get_text(" ", strip=True)[:3000]
        author_text_match = re.search(
            r"(?:written by|by|author[:\s]+|reviewed by|edited by)\s+([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
            body_text_snippet,
            re.IGNORECASE,
        )
        if author_text_match:
            author_found = True
            author_name = author_text_match.group(1).strip()[:60]

    if author_name and len(author_name.split()) > 4:
        author_name = " ".join(author_name.split()[:3])

    signals["author_found"] = author_found
    signals["author_name"] = author_name
    if author_found:
        score += 15  # site-wide: 15 pts

    # ── Author bio (10 pts — site-wide) ──────────────────────────────────────
    bio_patterns = re.compile(r"author|bio|about.*author|writer|contributor", re.I)
    bio_section = soup.find(True, {"class": bio_patterns}) or soup.find(True, {"id": bio_patterns})
    bio_text = bio_section.get_text(" ", strip=True) if bio_section else ""
    if not bio_text and author_found:
        author_page_link = soup.find("a", href=re.compile(r"/authors?/[^/]+", re.I))
        if author_page_link:
            bio_text = f"Author page: {author_name or 'linked'}"
    signals["has_author_bio"] = bool(bio_text)
    if bio_text:
        score += 10  # site-wide: 10 pts

    # ── Author credentials (10 pts — post-specific) ─────────────────────────
    # Only search bio text for credentials. The previous fallback searched
    # 5000 chars of body text which matched editorial mentions ("the author
    # of this book") rather than the post author's actual credentials.
    has_credentials = bool(AUTHOR_CREDENTIAL_PATTERNS.search(bio_text)) if bio_text else False
    if not has_credentials and author_name and ce:
        # Check eeat_metadata for credential signals from the full page chrome
        # (where author bios typically live, outside body_html)
        ce_author = ce.get("author_name", "") or ""
        # Only search a narrow window around the author name in body text (first 800 chars)
        if ce_author:
            nearby_text = soup.get_text(" ", strip=True)[:800]
            has_credentials = bool(AUTHOR_CREDENTIAL_PATTERNS.search(nearby_text))
    signals["has_author_credentials"] = has_credentials
    if has_credentials:
        score += 10  # post-specific: 10 pts

    # ── Date freshness (0/5/10/15 pts — post-specific, graduated) ──────────
    # Freshness is one of the most actionable E-E-A-T improvements. Graduated
    # scoring creates variance: recently-updated posts score higher than stale ones.
    # Uses modified_date if available, falls back to publish_date.
    time_tags = soup.find_all("time", attrs={"datetime": True})
    has_date = len(time_tags) > 0
    if not has_date:
        body_text_snippet = soup.get_text(" ", strip=True)[:3000]
        date_text_match = re.search(
            r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z.]*\s+\d{1,2},?\s+\d{4}"
            r"|(?:published|posted|updated|modified|last updated)\s*[:\s]*"
            r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z.]*\s+\d{1,2},?\s+\d{4}"
            r"|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}"
            r"|\d{4}[/\-]\d{1,2}[/\-]\d{1,2}))",
            body_text_snippet,
            re.IGNORECASE,
        )
        if date_text_match:
            has_date = True
    if not has_date and ce.get("has_visible_date"):
        has_date = True
    signals["has_visible_date"] = has_date

    # Graduated freshness: use most recent of modified_date / publish_date
    from datetime import datetime as _dt, timezone as _tz
    reference_date = modified_date or publish_date
    freshness_pts = 0
    if reference_date and has_date:
        now = _dt.now(_tz.utc)
        # Ensure reference_date is timezone-aware
        if reference_date.tzinfo is None:
            reference_date = reference_date.replace(tzinfo=_tz.utc)
        age_days = (now - reference_date).days
        if age_days <= 180:       # ≤ 6 months
            freshness_pts = 15
        elif age_days <= 365:     # 6-12 months
            freshness_pts = 10
        elif age_days <= 730:     # 1-2 years
            freshness_pts = 5
        # else: older than 2 years or no date = 0
    elif has_date and not reference_date:
        # Has a visible date but we don't know the actual date value — give base credit
        freshness_pts = 5
    signals["date_freshness_pts"] = freshness_pts
    if reference_date:
        ref = reference_date if reference_date.tzinfo else reference_date.replace(tzinfo=_tz.utc)
        signals["date_age_days"] = (_dt.now(_tz.utc) - ref).days
    else:
        signals["date_age_days"] = None
    score += freshness_pts

    # ── Visible updated/modified date (tracked separately for geo problem) ───
    # Specifically checks for "last updated"/"modified" language — NOT publish
    # dates. Used by geo_no_updated_date problem detection.
    has_updated_date = False
    _body_text_for_date = soup.get_text(" ", strip=True)[:3000]
    updated_text_match = re.search(
        r"(?:last updated|updated on|modified|updated)\s*[:\s]*"
        r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z.]*\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}"
        r"|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})",
        _body_text_for_date,
        re.IGNORECASE,
    )
    if updated_text_match:
        has_updated_date = True
    if not has_updated_date:
        for time_tag in time_tags:
            parent_text = time_tag.parent.get_text(" ", strip=True) if time_tag.parent else ""
            if re.search(r"(updated|modified|last updated)", parent_text, re.I):
                has_updated_date = True
                break
    signals["has_visible_updated_date"] = has_updated_date

    # ── Post-level outbound links to any external domain (15 pts) ────────────
    # Count links in body_html pointing to ANY external domain. A post linking
    # to Moz, HubSpot, or a research study shows the author did research.
    # Exclude same-domain links. Do NOT count social share buttons.
    links = soup.find_all("a", href=True)
    external_count = 0
    for a in links:
        href = str(a.get("href", "")).lower()
        if href.startswith(("http://", "https://")) and not re.search(
            r"(facebook\.com|twitter\.com|linkedin\.com|pinterest\.com|x\.com)"
            r"/(share|intent|sharer)", href
        ):
            external_count += 1
    signals["external_outbound_links"] = external_count
    signals["has_external_links"] = external_count >= 1
    if external_count >= 21:
        score += 15  # post-specific: heavily cited — research-heavy content
    elif external_count >= 11:
        score += 13  # well-cited — solid reference density
    elif external_count >= 6:
        score += 10  # moderately cited
    elif external_count >= 3:
        score += 7   # lightly cited
    elif external_count >= 1:
        score += 3   # minimal citations

    # ── Contact/About page link (10 pts — site-wide) ────────────────────────
    if "has_contact_link" in ce:
        has_contact = ce["has_contact_link"]
    else:
        has_contact = any(
            any(kw in str(a.get("href", "")).lower() or kw in a.get_text().lower()
                for kw in ["contact", "about", "team"])
            for a in links
        )
    signals["has_contact_link"] = has_contact
    if has_contact:
        score += 10  # site-wide: 10 pts

    # ── Post word count relative to site median (0-10 pts — post-specific, graduated) ──
    # Graduated scoring creates a 5-tier signal instead of binary above/below,
    # producing meaningful variance across the full range of content depths.
    signals["post_word_count"] = word_count
    signals["site_median_words"] = site_median_words
    word_count_pts = 0
    if site_median_words > 0:
        ratio = word_count / site_median_words
        if ratio >= 2.0:
            word_count_pts = 10   # 2x+ median: deep-dive content
        elif ratio >= 1.5:
            word_count_pts = 7    # 1.5-2x: comprehensive
        elif ratio >= 1.0:
            word_count_pts = 5    # 1.0-1.5x: above average
        elif ratio >= 0.5:
            word_count_pts = 2    # 0.5-1.0x: below average
        # else: < 0.5x = 0 pts (thin content)
    signals["word_count_above_median"] = word_count_pts >= 5  # backward compat
    signals["word_count_ratio"] = round(word_count / max(site_median_words, 1), 2)
    signals["word_count_pts"] = word_count_pts
    score += word_count_pts

    # ── Post H2 heading count (0-15 pts — post-specific, graduated) ─────────
    # Graduated scoring replaces the binary 3+ = 15 / else = 0.
    # The old binary gave 98.6% of Copyblogger posts 0 points (near-zero variance).
    # Graduated creates meaningful spread: even 1-2 H2s earn partial credit.
    #
    # NOTE: This counts H2s from the `headings` JSONB (parsed heading list from Step 1).
    # The Extraction score below counts H2s from body_html via BeautifulSoup.
    # These CAN differ: headings JSONB includes both H2+H3, while Extraction counts
    # only H2 tags in the raw HTML. A post with "H2 count: 0" here can still have
    # "H2s with direct answer: 1/3" in Extraction if headings JSONB wasn't populated.
    h2_count = sum(1 for h in (headings or []) if h.get("level") == "h2")
    signals["h2_count"] = h2_count
    signals["has_3plus_h2s"] = h2_count >= 3  # backward compat
    if h2_count >= 6:
        score += 15  # deeply structured — editorial-grade content
    elif h2_count >= 3:
        score += 10  # well-structured
    elif h2_count >= 1:
        score += 5   # some structure
    # else: 0 H2s = 0 pts

    # Author schema in JSON-LD — tracked as a signal for debugging, NOT scored.
    schema_tags = soup.find_all("script", attrs={"type": "application/ld+json"})
    has_author_schema = False
    for st in schema_tags:
        try:
            data = json.loads(st.string or "")
            if isinstance(data, list):
                data = data[0]
            if isinstance(data, dict) and "author" in data:
                has_author_schema = True
                break
        except (json.JSONDecodeError, Exception):
            continue
    signals["has_author_schema"] = has_author_schema

    # ── Thin-content cap ──────────────────────────────────────────────────────
    # Landing pages / stubs (< 300 words) shouldn't outscore substantive blog
    # posts on trust signals. Cap at 50 so site-wide signals don't inflate
    # pages with almost no content to evaluate.
    if word_count > 0 and word_count < 300:
        score = min(score, 50)
        signals["thin_content_capped"] = True

    signals["eeat_score"] = round(min(score, 100))
    return round(min(score, 100)), signals


# ── 3. Schema Score ───────────────────────────────────────────────────────────

def compute_schema_score(body_html: str, *, soup: BeautifulSoup | None = None) -> tuple[float, dict]:
    """0-100 schema markup score.

    Signals:
    - Has any JSON-LD schema (30 pts)
    - Has high-value schema type (Article/FAQ/HowTo) (30 pts)
    - Article schema has required fields: headline, datePublished, author, image (30 pts)
    - Multiple schema types (bonus 10 pts)
    """
    if soup is None:
        soup = _parse_html(body_html)
    signals: dict = {}
    score = 0.0

    schema_tags = soup.find_all("script", attrs={"type": "application/ld+json"})
    if not schema_tags:
        signals["has_schema"] = False
        signals["schema_types"] = []
        signals["schema_score"] = 0
        return 0.0, signals

    score += 30
    signals["has_schema"] = True

    schema_types: list[str] = []
    article_fields: dict[str, bool] = {}

    for st in schema_tags:
        try:
            data = json.loads(st.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                stype = item.get("@type", "")
                if isinstance(stype, list):
                    schema_types.extend(stype)
                elif stype:
                    schema_types.append(stype)

                # Check Article-type required fields
                if stype in ("Article", "BlogPosting", "NewsArticle", "TechArticle"):
                    article_fields["headline"] = bool(item.get("headline"))
                    article_fields["datePublished"] = bool(item.get("datePublished"))
                    article_fields["author"] = bool(item.get("author"))
                    article_fields["image"] = bool(item.get("image"))
                    article_fields["dateModified"] = bool(item.get("dateModified"))
        except (json.JSONDecodeError, Exception):
            continue

    signals["schema_types"] = schema_types

    # High-value schema type
    has_high_value = any(t in HIGH_VALUE_SCHEMA for t in schema_types)
    signals["has_high_value_schema"] = has_high_value
    if has_high_value:
        score += 30

    # Article completeness
    if article_fields:
        signals["article_fields"] = article_fields
        complete_fields = sum(article_fields.values())
        score += (complete_fields / len(article_fields)) * 30

    # Multiple schema types bonus
    unique_types = len(set(schema_types))
    if unique_types >= 2:
        score += 10

    signals["schema_score"] = round(min(score, 100))
    return round(min(score, 100)), signals


# ── 4. Extraction Score ───────────────────────────────────────────────────────

def compute_extraction_score(body_text: str, body_html: str, headings: list[dict], *, soup: BeautifulSoup | None = None) -> tuple[float, dict]:
    """0-100 score: how easily an AI can extract a direct answer.

    Total possible points: ~130. Capped at 100 via min(sum, 100).
    Same design as citability — intentional over-allocation.

    Signals:
    - Primary query answered in first 100 words (25 pts)
    - H2 sections start with concise answer (25 pts)
    - Clear definition paragraphs present (20 pts)
    - FAQ or Q&A structure (20 pts)
    - Structured lists under H2s (10 pts)
    """
    if soup is None:
        soup = _parse_html(body_html)
    text = body_text or ""
    signals: dict = {}
    score = 0.0

    # First 100 words — does it answer something directly?
    first_100 = " ".join(text.split()[:100])
    # Signals of direct answer: definitive statement, number, definition
    has_direct_opening = bool(
        re.search(r"\b(is|are|means|refers to|helps you|allows you|enables)\b", first_100, re.I)
        or re.search(r"\d+", first_100)
        or DEFINITION_PATTERNS.search(first_100)
    )
    signals["direct_opening"] = has_direct_opening
    if has_direct_opening:
        score += 25

    # H2 sections with concise first sentence
    h2_tags = soup.find_all(["h2", "h3"])
    h2_with_answer = 0
    for h2 in h2_tags:
        next_p = h2.find_next_sibling("p")
        if next_p:
            p_text = next_p.get_text(strip=True)
            words = len(p_text.split())
            # Concise answer: 15-80 words, starts with definitive statement
            if 15 <= words <= 80 and re.search(
                r"\b(is|are|means|you can|you should|this|the best|use|start)\b",
                p_text, re.I
            ):
                h2_with_answer += 1

    h2_answer_ratio = h2_with_answer / max(len(h2_tags), 1)
    signals["h2_with_direct_answer"] = h2_with_answer
    signals["total_h2"] = len(h2_tags)
    if h2_answer_ratio >= 0.5:
        score += 25
    elif h2_answer_ratio >= 0.25:
        score += 12

    # Definition paragraphs
    def_count = len(DEFINITION_PATTERNS.findall(text))
    signals["definition_count"] = def_count
    if def_count >= 2:
        score += 20
    elif def_count >= 1:
        score += 10

    # FAQ / Q&A structure — detect dedicated FAQ section (GEO-1 enhanced)
    # Look for explicit FAQ heading or consecutive question-format H3s
    has_faq_heading = bool(soup.find(["h2", "h3"], string=re.compile(r"(frequently asked|FAQ|common questions)", re.I)))
    # Count consecutive Q&A pairs: H3 with question mark followed by short paragraph
    h3_questions = 0
    for h3 in soup.find_all("h3"):
        h3_text = h3.get_text(strip=True)
        if h3_text.endswith("?") or re.match(r"^(what|how|why|when|where|which|who|can|does|is|are|should)\s", h3_text, re.I):
            next_p = h3.find_next_sibling("p")
            if next_p and len(next_p.get_text(strip=True).split()) <= 150:
                h3_questions += 1

    has_faq_section = has_faq_heading or h3_questions >= 3
    signals["has_faq_section"] = has_faq_section
    signals["faq_qa_pairs"] = h3_questions
    if has_faq_section and h3_questions >= 3:
        score += 20
    elif has_faq_section or h3_questions >= 2:
        score += 15
    elif h3_questions >= 1:
        score += 5

    # Standalone section test — sections should begin with topic sentence, not pronoun reference
    pronoun_starts = 0
    for h2 in soup.find_all("h2"):
        next_p = h2.find_next_sibling("p")
        if next_p:
            first_word = next_p.get_text(strip=True).split()[0] if next_p.get_text(strip=True) else ""
            if first_word.lower() in ("this", "it", "that", "these", "those", "they", "he", "she"):
                pronoun_starts += 1
    total_h2_count = len(soup.find_all("h2"))
    if total_h2_count < 2:
        # Posts with 0-1 H2s don't have enough sections to evaluate standalone-ness.
        # Score 0.5 (neutral) — don't reward or penalize lack of heading structure.
        # Only posts with real multi-section structure should earn the 10 points.
        standalone_ratio = 0.5
    else:
        standalone_ratio = 1 - (pronoun_starts / total_h2_count)
    signals["standalone_section_ratio"] = round(standalone_ratio, 2)
    if standalone_ratio >= 0.8:
        score += 10
    elif standalone_ratio >= 0.5:
        score += 5

    # Lists under H2 sections
    ul_ol_tags = soup.find_all(["ul", "ol"])
    list_items = sum(len(t.find_all("li")) for t in ul_ol_tags)
    signals["total_list_items"] = list_items
    if list_items >= 5:
        score += 10
    elif list_items >= 2:
        score += 5

    # GEO-5: Quote-worthiness — concise paragraphs with numbers/claims
    quotable_paragraphs = 0
    for p in soup.find_all("p"):
        p_text = p.get_text(strip=True)
        words = p_text.split()
        # Quotable: 10-40 words, contains a number, has a claim verb
        if 10 <= len(words) <= 40 and re.search(r"\d+%?", p_text):
            if re.search(r"\b(increase|decrease|reduce|improve|boost|grow|drop|rise|save|cost)\b", p_text, re.I):
                quotable_paragraphs += 1
    signals["quotable_paragraphs"] = quotable_paragraphs
    if quotable_paragraphs >= 3:
        score += 10
    elif quotable_paragraphs >= 1:
        score += 5

    # GEO-5: Comparison table extractability
    tables = soup.find_all("table")
    extractable_tables = 0
    for table in tables:
        rows = table.find_all("tr")
        headers = table.find_all("th")
        if len(rows) >= 3 and len(headers) >= 2:
            extractable_tables += 1
    signals["extractable_tables"] = extractable_tables
    if extractable_tables >= 1:
        score += 10

    signals["extraction_score"] = round(min(score, 100))
    return round(min(score, 100)), signals


# ── Main service ──────────────────────────────────────────────────────────────

class AICitabilityService:
    """Score all posts for a site on AI-era readiness dimensions."""

    async def score_site(self, db: asyncpg.Connection, site_id: UUID) -> dict[str, float]:
        """Compute AI readiness scores for all posts in a site.

        Uses full body_text and body_html from the posts table — NOT the
        truncated 20K-char text used for embeddings. This is important:
        long posts get scored on their complete content, even if their
        embedding only represents the first ~5000 tokens.

        Returns aggregate stats: avg scores, distribution, top/bottom posts.
        """
        logger.info("AI Citability scoring for site %s", site_id)

        rows = await db.fetch(
            """
            SELECT p.id, p.body_text, p.body_html, p.headings, p.eeat_metadata,
                   p.word_count, p.publish_date, p.modified_date
            FROM posts p
            LEFT JOIN post_health_scores phs ON phs.post_id = p.id
            WHERE p.site_id = $1 AND p.body_text IS NOT NULL
            """,
            site_id,
        )

        if not rows:
            logger.warning("No posts to score for site %s", site_id)
            return {}

        total = len(rows)
        logger.info("Scoring %d posts for AI readiness", total)

        # Calculate site median word count for E-E-A-T scoring
        word_counts = sorted(r.get("word_count") or 0 for r in rows)
        site_median_words = word_counts[len(word_counts) // 2] if word_counts else 0

        scores_cite = []
        scores_eeat = []
        scores_schema = []
        scores_extract = []

        for i, row in enumerate(rows):
            body_text = row["body_text"] or ""
            body_html = row["body_html"] or ""
            headings = row["headings"] or []
            if isinstance(headings, str):
                headings = json.loads(headings) if headings.strip() else []
            post_word_count = row.get("word_count") or len(body_text.split())

            # Parse crawl-time E-E-A-T metadata (extracted from full page HTML)
            crawl_eeat = row.get("eeat_metadata") or {}
            if isinstance(crawl_eeat, str):
                crawl_eeat = json.loads(crawl_eeat) if crawl_eeat.strip() else {}
            if isinstance(crawl_eeat, str):
                crawl_eeat = json.loads(crawl_eeat)

            # Parse HTML once, pass pre-parsed soup to all 4 scorers (4x fewer parses)
            parsed_soup = _parse_html(body_html)

            cite_score, cite_signals = compute_citability_score(body_text, body_html, soup=parsed_soup)
            eeat_score, eeat_signals = compute_eeat_score(
                body_html, crawl_eeat=crawl_eeat,
                headings=headings, word_count=post_word_count,
                site_median_words=site_median_words,
                publish_date=row.get("publish_date"),
                modified_date=row.get("modified_date"),
                soup=parsed_soup,
            )
            schema_score, schema_signals = compute_schema_score(body_html, soup=parsed_soup)
            extract_score, extract_signals = compute_extraction_score(body_text, body_html, headings, soup=parsed_soup)

            all_signals = {
                **cite_signals,
                **{f"eeat_{k}": v for k, v in eeat_signals.items()},
                **{f"schema_{k}": v for k, v in schema_signals.items()},
                **{f"extract_{k}": v for k, v in extract_signals.items()},
            }

            await db.execute(
                """
                INSERT INTO post_health_scores (post_id, ai_citability_score, eeat_score, schema_score, extraction_score, ai_signals)
                VALUES ($6, $1, $2, $3, $4, $5)
                ON CONFLICT (post_id) DO UPDATE SET
                    ai_citability_score = EXCLUDED.ai_citability_score,
                    eeat_score = EXCLUDED.eeat_score,
                    schema_score = EXCLUDED.schema_score,
                    extraction_score = EXCLUDED.extraction_score,
                    ai_signals = EXCLUDED.ai_signals
                """,
                float(cite_score), float(eeat_score),
                float(schema_score), float(extract_score),
                json.dumps(all_signals),
                row["id"],
            )

            scores_cite.append(cite_score)
            scores_eeat.append(eeat_score)
            scores_schema.append(schema_score)
            scores_extract.append(extract_score)

            if (i + 1) % 100 == 0:
                logger.info("AI scoring: %d/%d posts done", i + 1, total)

        def _avg(lst: list) -> float:
            return round(sum(lst) / len(lst), 1) if lst else 0.0

        result = {
            "total_scored": total,
            "avg_citability": _avg(scores_cite),
            "avg_eeat": _avg(scores_eeat),
            "avg_schema": _avg(scores_schema),
            "avg_extraction": _avg(scores_extract),
            "pct_has_schema": round(sum(1 for s in scores_schema if s > 0) / max(total, 1) * 100, 1),
            "pct_ai_ready": round(sum(1 for s in scores_cite if s >= 60) / max(total, 1) * 100, 1),
        }

        logger.info(
            "AI scoring complete for site %s — avg citability=%.1f eeat=%.1f schema=%.1f extraction=%.1f",
            site_id, result["avg_citability"], result["avg_eeat"],
            result["avg_schema"], result["avg_extraction"],
        )
        return result


# ── Problem detection helpers ─────────────────────────────────────────────────

def generate_ai_problems(post_id: UUID, title: str,
                          cite: float, eeat: float,
                          schema: float, extract: float,
                          signals: dict) -> list[dict]:
    """Return problem dicts for AI readiness issues — plugs into problem detection."""
    problems = []

    if cite < 40:
        problems.append({
            "post_id": post_id,
            "problem_type": "low_ai_citability",
            "severity": "high" if cite < 20 else "medium",
            "description": (
                f"AI Citability Score: {int(cite)}/100. "
                "This post lacks signals that AI systems use when deciding what to cite: "
                "original data, first-person experience, data tables, or numbered sequences."
            ),
            "metadata": {"citability_score": cite, "signals": signals},
        })

    if eeat < 40:
        missing = []
        if not signals.get("eeat_author_found"):
            missing.append("author byline")
        if not signals.get("eeat_has_author_bio"):
            missing.append("author bio")
        if not signals.get("eeat_has_visible_date"):
            missing.append("visible date")
        if not signals.get("eeat_has_external_links"):
            missing.append("outbound links")
        if not signals.get("eeat_has_3plus_h2s"):
            missing.append("structured H2 sections")
        problems.append({
            "post_id": post_id,
            "problem_type": "weak_eeat",
            "severity": "high" if eeat < 20 else "medium",
            "description": (
                f"Weak E-E-A-T signals (score: {int(eeat)}/100). "
                f"Missing: {', '.join(missing) if missing else 'multiple trust signals'}. "
                "96% of AI Overview citations come from high E-E-A-T content."
            ),
            "metadata": {"eeat_score": eeat, "missing": missing},
        })

    if schema < 30:
        problems.append({
            "post_id": post_id,
            "problem_type": "missing_schema",
            "severity": "medium",
            "description": (
                f"No structured data (schema score: {int(schema)}/100). "
                "Pages with Article/FAQ/HowTo JSON-LD schema are significantly more likely "
                "to be cited in AI answers. Add at minimum: Article schema with headline, "
                "datePublished, author, and image."
            ),
            "metadata": {"schema_score": schema, "schema_types": signals.get("schema_types", [])},
        })

    if extract < 40:
        problems.append({
            "post_id": post_id,
            "problem_type": "poor_ai_structure",
            "severity": "medium",
            "description": (
                f"Poor AI extraction structure (score: {int(extract)}/100). "
                "This post doesn't answer its primary query in the first 200 words, "
                "and H2 sections don't start with concise direct answers. "
                "AI systems prefer content that front-loads answers."
            ),
            "metadata": {"extraction_score": extract},
        })

    # ── GEO-specific granular problems (GEO-8) ──

    # No FAQ section
    if not signals.get("has_faq_section") and not signals.get("extract_has_faq_section"):
        problems.append({
            "post_id": post_id,
            "problem_type": "geo_no_faq_section",
            "severity": "medium",
            "description": (
                "No FAQ section detected. Posts with structured FAQ sections are "
                "significantly more likely to be cited by AI systems. Add 3-5 Q&A pairs "
                "covering common questions about this topic."
            ),
            "metadata": {},
        })

    # Low question-format headers — also fires on posts with 0 H2s (adding
    # question-format H2s is a double win: heading structure + GEO optimization)
    total_headers = signals.get("total_headers", 0)
    q_ratio = signals.get("question_header_ratio", 0)
    if total_headers == 0:
        problems.append({
            "post_id": post_id,
            "problem_type": "geo_no_question_headers",
            "severity": "medium",
            "description": (
                "No H2/H3 headers detected. Adding question-format headers (What is...?, "
                "How to...?) improves both content structure and AI discoverability. "
                "AI systems match natural language prompts to question headers."
            ),
            "metadata": {"question_header_ratio": 0, "total_headers": 0},
        })
    elif q_ratio < 0.3 and total_headers >= 3:
        problems.append({
            "post_id": post_id,
            "problem_type": "geo_no_question_headers",
            "severity": "medium",
            "description": (
                f"Only {int(q_ratio * 100)}% of headers are question-format "
                f"({signals.get('question_headers', 0)} of {total_headers}). "
                "AI systems match natural language prompts to question headers. "
                "Top AI-cited content typically uses 25-35% question-format headers."
            ),
            "metadata": {"question_header_ratio": q_ratio},
        })

    # Low data density
    data_density = signals.get("data_density_per_200w", 0)
    if data_density < 0.5:
        problems.append({
            "post_id": post_id,
            "problem_type": "geo_low_data_density",
            "severity": "medium",
            "description": (
                f"Data density: {data_density:.1f} data points per 200 words (target: 1.0). "
                "AI systems preferentially cite content with specific statistics. "
                "Add more numbers, percentages, and attributed data."
            ),
            "metadata": {"data_density_per_200w": data_density},
        })

    # No answer-first structure
    if not signals.get("answer_first_200w") and not signals.get("direct_opening"):
        problems.append({
            "post_id": post_id,
            "problem_type": "geo_no_answer_first",
            "severity": "medium",
            "description": (
                "The first 200 words don't directly answer the query. "
                "AI systems extract the first passage that answers a prompt. "
                "Add a TL;DR with a direct answer and at least one data point."
            ),
            "metadata": {},
        })

    # Has FAQ content but missing FAQPage schema
    has_faq_content = signals.get("has_faq_section") or signals.get("extract_has_faq_section") or signals.get("faq_qa_pairs", 0) >= 2
    has_faq_schema = "FAQPage" in signals.get("schema_types", [])
    if has_faq_content and not has_faq_schema:
        problems.append({
            "post_id": post_id,
            "problem_type": "geo_missing_faq_schema",
            "severity": "high",
            "description": (
                "This post has FAQ content but no FAQPage JSON-LD schema. "
                "Adding structured data makes Q&A pairs directly extractable by AI "
                "and increases eligibility for Google rich results."
            ),
            "metadata": {},
        })

    # No visible "last updated" / "modified" date signal.
    # Note: this is NOT about publish_date (which 99%+ of posts have). This checks
    # for a visible UPDATED/MODIFIED signal — a separate concept. A post published
    # in 2020 with a visible publish date but no "last updated" correctly triggers
    # this problem because it looks stale to AI systems even if the content is current.
    # Uses has_visible_updated_date (checks for "updated"/"modified" language)
    # NOT has_visible_date (which is True for any date including publish dates).
    if not signals.get("eeat_has_visible_updated_date"):
        problems.append({
            "post_id": post_id,
            "problem_type": "geo_no_updated_date",
            "severity": "low",
            "description": (
                "No visible 'Last updated' or 'Modified' date detected on the page. "
                "AI systems favor content with recent modification signals. "
                "Add a visible 'Last updated: [date]' timestamp to show freshness."
            ),
            "metadata": {},
        })

    return problems
