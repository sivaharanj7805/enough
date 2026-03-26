"""Cannibalization detection via embedding cosine similarity + GSC query overlap.

Research-informed approach (two-signal detection):
1. Embedding cosine similarity between posts in the same cluster
2. GSC query overlap — posts ranking for the same search queries

THRESHOLD CALIBRATION:
Thresholds are auto-calibrated per site using the pairwise similarity
distribution. This handles niche sites (higher baseline similarity)
vs general blogs (lower baseline). Calibration uses 85th/92nd/97th
percentiles with absolute floors of 0.30/0.40/0.50.

Default thresholds (text-embedding-3-small):
- flag: 0.40 (review), high: 0.50 (action needed), critical: 0.60 (near-duplicate)

PERFORMANCE:
For clusters with 20+ posts, uses HNSW index pre-filtering to avoid
O(n²) pair scans. Finds top-10 nearest neighbors per post via pgvector's
HNSW index, then only evaluates those candidate pairs.

The "stronger post" is determined by composite health score + traffic.
"""

import logging
import re
from itertools import combinations
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)

# Cosine similarity thresholds for text-embedding-3-small
# CRITICAL: This model produces LOWER similarity scores than ada-002.
# Research (OpenAI community, 2024): content that scored 0.70+ with ada-002
# scores ~0.40 with text-embedding-3-small. Thresholds must be calibrated
# accordingly. Same-topic content typically scores 0.45-0.55.
#
# These defaults should be tuned per-site after initial embedding generation.
# Run: SELECT 1 - (a.embedding <=> b.embedding) FROM post_embeddings a, b
# on known-cannibalized pairs to calibrate.
COSINE_THRESHOLD_FLAG = 0.45    # Flag for review (raised from 0.40 to reduce false positives on niche sites)
COSINE_THRESHOLD_HIGH = 0.55    # High confidence cannibalization
COSINE_THRESHOLD_CRITICAL = 0.65  # Near-duplicate content

# Min shared queries for query-only cannibalization
MIN_SHARED_QUERIES = 3  # Require 3+ shared queries — single shared query is too weak a signal


# ── Blended cannibalization scoring ──────────────────────────────────────────
#
# Cannibalization = Google doesn't know which page to show for a given query.
# The ground truth test: "Would a human typing a single search query be
# satisfied by either post?"
#
# Without GSC data, we approximate this by checking whether two posts target
# the same inferred keyword (from URL slug + title), serve the same search
# intent, and cover the same subtopics (from H2 headings).
#
# The blended score replaces raw cosine similarity as the primary signal.
# Cosine captures topical similarity but NOT keyword competition.
# Two SEO tool reviews are topically similar but never compete for the
# same query if they review different products.

_SLUG_STOPS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "is", "are", "how", "what", "why",
    "your", "you", "that", "this", "from", "it", "its", "can",
    "www", "com", "html", "php", "blog", "post", "page",
})

# Intent modifier groups — posts only cannibalize when they share both the
# same entity AND the same intent group
_INTENT_GROUPS = {
    "learning": {"guide", "how", "tutorial", "strategies", "tips", "techniques",
                 "ways", "steps", "explained", "introduction", "basics",
                 "beginners", "learn", "definitive", "complete", "ultimate",
                 "simple", "comprehensive", "checklist", "course"},
    "browsing": {"examples", "templates", "inspiration", "ideas", "samples",
                 "list", "collection", "roundup"},
    "evaluation": {"review", "comparison", "versus", "alternative", "alternatives",
                   "pricing", "pros", "cons", "worth"},
    "research": {"statistics", "stats", "report", "study", "data", "survey",
                 "analyzed", "analysis", "research", "findings", "benchmark",
                 "trends", "state"},
    "shopping": {"tools", "software", "resources", "platforms", "services",
                 "products", "apps", "programs", "deals"},
}

# Review template H2 keywords
_REVIEW_H2S = frozenset({
    "features", "pricing", "pros", "cons", "verdict", "alternatives",
    "overview", "review", "summary", "plans", "integrations",
    "key features", "who is it for", "bottom line",
    "free trial", "customer support", "ease of use",
})

# Common title suffixes to strip when extracting the core keyword
_TITLE_SUFFIXES = re.compile(
    r"\s*[-–:|]\s*.+$"  # Strip "Title - Site Name" / "Title: Subtitle"
)
_TITLE_FORMAT_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "is", "are", "how", "what", "why",
    "your", "you", "that", "this", "from", "it", "its", "can",
    "get", "best", "top", "new", "most", "more", "here", "our",
    "guide", "complete", "definitive", "ultimate", "simple", "step",
})


def _heading_text(h) -> str:
    """Extract text from a heading (handles both dict and string formats)."""
    if isinstance(h, dict):
        return (h.get("text") or "").lower().strip()
    return str(h).lower().strip() if h else ""


# Format words in URL slugs that indicate article type, not topic
_SLUG_FORMAT_WORDS = frozenset({
    "review", "guide", "tutorial", "tips", "strategies", "examples",
    "comparison", "alternative", "alternatives", "report", "study",
    "statistics", "stats", "tools", "best", "free", "hub",
})


def _extract_slug_core(url: str) -> set[str]:
    """Extract core topic keywords from URL slug, stripping format words.

    /serpstat-review → {"serpstat"}
    /link-building-strategies → {"link", "building"}
    /ecommerce-website-examples → {"ecommerce", "website"}
    """
    from urllib.parse import urlparse
    path = urlparse(url).path.strip("/")
    slug = path.split("/")[-1] if "/" in path else path
    words = set(re.findall(r"[a-z]{3,}", slug.lower()))
    return words - _SLUG_STOPS - _SLUG_FORMAT_WORDS


# Format markers in titles — strip these to extract the topic entity.
# "SEO Copywriting: The Definitive Guide" → strip ": The Definitive Guide" → "seo copywriting"
_TITLE_FORMAT_MARKERS = re.compile(
    r"(?:"
    r":\s*(?:the|a|an)?\s*(?:definitive|complete|comprehensive|ultimate|essential|practical)\s+guide"
    r"|:\s*(?:a\s+)?step[- ]by[- ]step\s+guide"
    r"|:\s*(?:a\s+)?beginner'?s?\s+guide"
    r"|:\s*(?:a\s+)?comprehensive\s+checklist"
    r"|:\s*how\s+to\s+.+"
    r"|:\s*what\s+(?:is|are)\s+.+"
    r"|:\s*everything\s+you\s+need\s+to\s+know"
    r"|:\s*(?:a\s+)?case\s+study"
    r"|:\s*(?:a\s+)?complete\s+list"
    r")"
    r"\s*(?:[-–|].+)?$",  # Also strip trailing " - Site Name"
    re.IGNORECASE,
)

# Leading format patterns: "How to X", "What Is X", "N Ways to X"
_TITLE_LEADING_FORMAT = re.compile(
    r"^(?:"
    r"how\s+to\s+"
    r"|what\s+(?:is|are)\s+"
    r"|\d+\s+(?:ways?|tips?|steps?|methods?|strategies|techniques|examples?|types?)\s+(?:to|of|for)\s+"
    r")",
    re.IGNORECASE,
)


def _extract_title_entity(title: str) -> str | None:
    """Extract the topic entity from a title by stripping format markers.

    Works for any title format, not just reviews:
    "Serpstat Review: Is This SEO Tool Worth It?" → "serpstat"
    "SEO Copywriting: The Definitive Guide" → "seo copywriting"
    "Google RankBrain: The Definitive Guide" → "google rankbrain"
    "Link Building: A Complete Guide" → "link building"
    "How to Build Links With Content Marketing" → "build links content marketing"
    "9 Ecommerce Website Examples" → "ecommerce website"
    """
    t = title.lower().strip()

    # Pattern 1: "X Review" / "X vs Y"
    m = re.match(r"^(.+?)\s+(review|vs\.?|versus|comparison|alternative)", t)
    if m:
        entity = m.group(1).strip().rstrip(":").strip()
        entity = re.sub(r"^(the|a|an)\s+", "", entity)
        return entity if len(entity) >= 2 else None

    # Pattern 2: "Review of X"
    m = re.match(r"^review\s*[:of]+\s*(.+?)(\s*[-–|]|$)", t)
    if m:
        return m.group(1).strip()

    # Pattern 3: "Topic: The Definitive Guide" / "Topic: A Complete Guide" etc.
    m = _TITLE_FORMAT_MARKERS.search(t)
    if m:
        entity = t[:m.start()].strip().rstrip(":").strip()
        entity = re.sub(r"^(the|a|an)\s+", "", entity)
        return entity if len(entity) >= 2 else None

    # Pattern 3b: "X Case Study: ..." — format word BEFORE the colon
    m = re.match(r"^(.+?)\s+(?:case\s+study|report|checklist|cheat\s+sheet)\s*:", t)
    if m:
        entity = m.group(1).strip()
        entity = re.sub(r"^(the|a|an)\s+", "", entity)
        return entity if len(entity) >= 2 else None

    # Pattern 4: "How to X..." / "What Is X..." / "N Ways to X..."
    m = _TITLE_LEADING_FORMAT.match(t)
    if m:
        remainder = t[m.end():].strip()
        # Strip trailing site name / subtitle
        remainder = re.sub(r"\s*[-–|:].+$", "", remainder)
        # Strip trailing format words
        remainder = re.sub(
            r"\s+(?:in\s+\d{4}|for\s+\d{4}|guide|tutorial|tips|strategies)$",
            "", remainder,
        )
        if len(remainder) >= 3:
            return remainder

    # Pattern 5: "N Best/Top X..." — extract X
    m = re.match(r"^\d+\s+(?:best|top|key|essential|proven|incredible|awesome)\s+(.+?)(?:\s+(?:in|for)\s+\d{4})?$", t)
    if m:
        entity = m.group(1).strip()
        # Strip trailing format words
        entity = re.sub(r"\s+(?:to\s+try|you\s+should|for\s+.+)$", "", entity)
        return entity if len(entity) >= 3 else None

    return None


def _extract_title_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a title, stripping format words."""
    # Remove site name suffix ("Title - Site Name")
    t = _TITLE_SUFFIXES.sub("", title)
    words = set(re.findall(r"[a-zA-Z]{3,}", t.lower()))
    return words - _TITLE_FORMAT_WORDS


def _classify_intent_group(title: str, url: str) -> str | None:
    """Classify a post's search intent group from title + URL.

    Returns one of: learning, browsing, evaluation, research, shopping, or None.
    """
    combined = f"{title} {url}".lower()
    words = set(re.findall(r"[a-z]{3,}", combined))
    best_group = None
    best_overlap = 0
    for group, keywords in _INTENT_GROUPS.items():
        overlap = len(words & keywords)
        if overlap > best_overlap:
            best_overlap = overlap
            best_group = group
    return best_group if best_overlap >= 1 else None


def _h2_subtopic_jaccard(headings_a: list, headings_b: list) -> float:
    """Compute Jaccard similarity on H2 heading content keywords.

    Strips entity names (from title) so that "Serpstat Features" and
    "Ahrefs Features" don't match on the entity, only on the subtopic word.
    """
    def _kw_set(headings: list) -> set[str]:
        words = set()
        for h in headings:
            text = _heading_text(h)
            if text:
                words.update(w for w in re.findall(r"[a-z]{3,}", text)
                             if w not in _TITLE_FORMAT_WORDS)
        return words

    kw_a = _kw_set(headings_a)
    kw_b = _kw_set(headings_b)
    if not kw_a or not kw_b:
        return 0.0
    intersection = kw_a & kw_b
    union = kw_a | kw_b
    return len(intersection) / len(union) if union else 0.0


def _is_review_template(headings: list) -> bool:
    """Check if headings follow a review article template."""
    h_keywords = set()
    for h in headings:
        text = _heading_text(h)
        if text:
            h_keywords.update(re.findall(r"[a-z]+", text))
    return len(h_keywords & _REVIEW_H2S) >= 3


def compute_blended_cannibalization_score(
    post_a: dict, post_b: dict,
    headings_a: list, headings_b: list,
    cosine_sim: float | None,
) -> tuple[float, str]:
    """Compute a blended cannibalization score (0.0 to 1.0) and severity tier.

    The blended score answers: "Would a human typing a single search query
    be satisfied by either post?" — which is the real definition of cannibalization.

    Signals and weights:
      - Cosine embedding similarity:  25% (broad topical overlap baseline)
      - URL slug keyword overlap:     25% (same inferred target keyword)
      - Title entity + intent match:  30% (same topic + same search purpose)
      - H2 subtopic Jaccard:          20% (posts cover the same specific subtopics)

    Returns (blended_score, severity_tier).

    Severity tiers:
      critical: blended > 0.80 — near-duplicates, merge or redirect
      high:     blended > 0.55 — genuine query competition, differentiate
      medium:   blended > 0.35 — potential overlap, monitor
      low:      blended <= 0.35 — content series, don't flag
    """
    title_a = post_a.get("title", "")
    title_b = post_b.get("title", "")
    url_a = post_a.get("url", "")
    url_b = post_b.get("url", "")

    # ── Signal 1: Cosine similarity (25%) ──
    cosine_component = min((cosine_sim or 0.0), 1.0)

    # ── Signal 2: URL slug keyword overlap (25%) ──
    slug_a = _extract_slug_core(url_a)
    slug_b = _extract_slug_core(url_b)
    if slug_a and slug_b:
        slug_intersection = slug_a & slug_b
        slug_union = slug_a | slug_b
        slug_overlap = len(slug_intersection) / len(slug_union) if slug_union else 0.0
    else:
        slug_overlap = 0.0

    # ── Signal 3: Title entity + intent match (30%) ──
    entity_a = _extract_title_entity(title_a)
    entity_b = _extract_title_entity(title_b)

    # Entity match score: 1.0 if same entity, 0.0 if different named entities,
    # 0.5 if no entity detected (can't tell)
    entities_are_different = False
    if entity_a and entity_b:
        if entity_a == entity_b:
            entity_match = 1.0
        else:
            entity_match = 0.0
            entities_are_different = True
    elif entity_a or entity_b:
        # One has an entity, the other doesn't — probably different content types
        entity_match = 0.2
    else:
        # Neither has a clear entity — fall back to title keyword overlap
        title_kw_a = _extract_title_keywords(title_a)
        title_kw_b = _extract_title_keywords(title_b)
        if title_kw_a and title_kw_b:
            title_union = title_kw_a | title_kw_b
            entity_match = len(title_kw_a & title_kw_b) / len(title_union) if title_union else 0.0
        else:
            entity_match = 0.0

    # Intent group match: 1.0 if same group, 0.3 if different groups, 0.5 if unknown
    # BUT: if entities are explicitly different, intent match is irrelevant —
    # "Serpstat Review" and "Ahrefs Review" have the same intent (evaluation)
    # but they don't compete because they're about different products.
    intent_a = _classify_intent_group(title_a, url_a)
    intent_b = _classify_intent_group(title_b, url_b)
    if entities_are_different:
        # Different named entities → intent match doesn't matter
        intent_match = 0.0
    elif intent_a and intent_b:
        intent_match = 1.0 if intent_a == intent_b else 0.3
    else:
        intent_match = 0.5

    # Combined entity+intent: both must match for high score
    entity_intent_score = entity_match * 0.6 + intent_match * 0.4

    # ── Signal 4: H2 subtopic Jaccard (20%) ──
    h2_jaccard = _h2_subtopic_jaccard(headings_a, headings_b)

    # If both posts are review templates reviewing different entities, zero out H2 score
    # (structurally identical H2s about different products shouldn't count)
    if entity_a and entity_b and entity_a != entity_b:
        if _is_review_template(headings_a) and _is_review_template(headings_b):
            h2_jaccard = 0.0

    # ── Blended score ──
    blended = (
        0.25 * cosine_component
        + 0.25 * slug_overlap
        + 0.30 * entity_intent_score
        + 0.20 * h2_jaccard
    )

    # ── Severity tier ──
    if blended > 0.80:
        tier = "critical"
    elif blended > 0.55:
        tier = "high"
    elif blended > 0.35:
        tier = "medium"
    else:
        tier = "low"  # Content series — don't flag

    return blended, tier


class CannibalizationDetector:
    """Detect cannibalization within topic clusters using embeddings + GSC."""

    async def calibrate_thresholds(
        self, db: asyncpg.Connection, site_id: UUID,
    ) -> dict[str, float]:
        """Auto-calibrate cosine similarity thresholds for a specific site.

        Computes the pairwise cosine similarity distribution across all posts
        and sets thresholds at the 85th and 95th percentiles. This adapts to
        the site's content: a niche site about "React hooks" will have higher
        baseline similarity than a general tech blog.

        Stores calibrated thresholds in the sites table and returns them.
        """
        logger.info("Calibrating cosine thresholds for site %s", site_id)

        # Get a sample of pairwise similarities (cap at 500 pairs for perf)
        similarities = await db.fetch(
            """
            SELECT 1 - (a.embedding <=> b.embedding) AS similarity
            FROM post_embeddings a
            JOIN posts pa ON pa.id = a.post_id
            JOIN post_embeddings b ON b.post_id > a.post_id
            JOIN posts pb ON pb.id = b.post_id
            WHERE pa.site_id = $1 AND pb.site_id = $1
            ORDER BY RANDOM()
            LIMIT 500
            """,
            site_id,
        )

        if len(similarities) < 10:
            logger.info(
                "Too few pairs (%d) to calibrate — using defaults", len(similarities),
            )
            return {
                "flag": COSINE_THRESHOLD_FLAG,
                "high": COSINE_THRESHOLD_HIGH,
                "critical": COSINE_THRESHOLD_CRITICAL,
            }

        import numpy as np
        sims = np.array([float(r["similarity"]) for r in similarities])

        # Use percentiles: flag=85th, high=92nd, critical=97th
        p85 = float(np.percentile(sims, 85))
        p92 = float(np.percentile(sims, 92))
        p97 = float(np.percentile(sims, 97))

        # Floor: don't go below absolute minimums
        # Floors calibrated for text-embedding-3-small which produces lower absolute
        # cosine similarities (~0.35-0.45 for same-topic content vs 0.60+ in ada-002).
        # Original floors of 0.50/0.70/0.85 systematically missed real cannibalization.
        flag = max(p85, 0.40)
        high = max(p92, 0.50)
        critical = max(p97, 0.60)

        logger.info(
            "Calibrated thresholds for site %s: flag=%.3f (p85), high=%.3f (p92), "
            "critical=%.3f (p97) | distribution: min=%.3f, median=%.3f, max=%.3f",
            site_id, flag, high, critical,
            float(np.min(sims)), float(np.median(sims)), float(np.max(sims)),
        )

        # Store in sites table metadata
        import json
        calibration_meta = json.dumps({
            "cosine_threshold_flag": round(flag, 4),
            "cosine_threshold_high": round(high, 4),
            "cosine_threshold_critical": round(critical, 4),
        })
        await db.execute(
            """
            UPDATE sites SET metadata = COALESCE(metadata, '{}'::jsonb) || $1::jsonb
            WHERE id = $2
            """,
            calibration_meta,
            site_id,
        )

        return {"flag": flag, "high": high, "critical": critical}

    async def detect_for_site(
        self, db: asyncpg.Connection, site_id: UUID,
        max_pairs: int = 500,
    ) -> int:
        """Run cannibalization detection across all clusters for a site.

        Auto-calibrates thresholds on first run, then uses site-specific
        thresholds stored in the sites table. Limits output to max_pairs
        most severe pairs for actionability.

        Returns the number of cannibalization pairs found.
        """
        try:
            return await self._detect_for_site_impl(db, site_id, max_pairs)
        except Exception as e:
            logger.error("Cannibalization detection failed for site %s: %s", site_id, e, exc_info=True)
            raise

    async def _detect_for_site_impl(
        self, db: asyncpg.Connection, site_id: UUID,
        max_pairs: int = 500,
    ) -> int:
        logger.info("Starting cannibalization detection for site %s", site_id)

        # Pre-filter: detect and flag duplicate content (different URLs, same content)
        dupes = await db.fetch("""
            SELECT p1.id as id1, p2.id as id2, p1.url as url1, p2.url as url2
            FROM posts p1
            JOIN posts p2 ON p1.content_hash = p2.content_hash
                AND p1.id < p2.id AND p1.site_id = p2.site_id
            WHERE p1.site_id = $1 AND p1.content_hash IS NOT NULL
        """, site_id)
        if dupes:
            logger.info("Found %d duplicate content pairs (same content, different URLs)", len(dupes))
            for d in dupes[:5]:
                logger.info("  Duplicate: %s ↔ %s", d["url1"][:50], d["url2"][:50])

        # Load site-specific calibrated thresholds (or calibrate now)
        site_meta = await db.fetchval(
            "SELECT metadata FROM sites WHERE id = $1", site_id,
        )
        if site_meta and isinstance(site_meta, dict) and "cosine_threshold_flag" in site_meta:
            thresholds = {
                "flag": site_meta["cosine_threshold_flag"],
                "high": site_meta["cosine_threshold_high"],
                "critical": site_meta["cosine_threshold_critical"],
            }
            logger.info(
                "Using calibrated thresholds for site %s: %s", site_id, thresholds,
            )
        else:
            thresholds = await self.calibrate_thresholds(db, site_id)

        # Only scan leaf clusters (no children) to avoid redundant pairwise work
        # on parent clusters whose posts are already covered by child clusters
        clusters = await db.fetch(
            """SELECT id, post_count FROM clusters WHERE site_id = $1
               AND id NOT IN (
                   SELECT parent_cluster_id FROM clusters
                   WHERE parent_cluster_id IS NOT NULL AND site_id = $1
               )""",
            site_id,
        )

        if not clusters:
            logger.warning("No clusters for site %s — run clustering first", site_id)
            return 0

        # Clear old pairs
        cluster_ids = [r["id"] for r in clusters]
        await db.execute(
            "DELETE FROM cannibalization_pairs WHERE cluster_id = ANY($1::uuid[])",
            cluster_ids,
        )

        total_pairs = 0
        for cluster_row in clusters:
            if cluster_row["post_count"] < 2:
                continue
            pairs = await self._detect_in_cluster(
                db, cluster_row["id"], site_id, thresholds=thresholds,
            )
            total_pairs += pairs

        # Scale max_pairs with site size (500 minimum, up to 1500 for large sites)
        total_posts = sum(r["post_count"] for r in clusters if r.get("post_count"))
        if max_pairs == 500:  # default, not user-overridden
            max_pairs = max(500, min(total_posts * 3, 1500))

        # Prune to max_pairs — keep only the most severe
        if total_pairs > max_pairs:
            await db.execute("""
                DELETE FROM cannibalization_pairs
                WHERE id NOT IN (
                    SELECT cp.id FROM cannibalization_pairs cp
                    JOIN posts p ON cp.post_a_id = p.id
                    WHERE p.site_id = $1
                    ORDER BY cp.cosine_similarity DESC
                    LIMIT $2
                )
                AND post_a_id IN (SELECT id FROM posts WHERE site_id = $1)
            """, site_id, max_pairs)
            pruned = total_pairs - max_pairs
            logger.info("Pruned %d low-severity pairs, keeping top %d", pruned, max_pairs)
            total_pairs = max_pairs

        logger.info(
            "Cannibalization detection complete for site %s — %d pairs found",
            site_id, total_pairs,
        )
        return total_pairs

    async def _detect_in_cluster(
        self, db: asyncpg.Connection, cluster_id: UUID, site_id: UUID,
        thresholds: dict[str, float] | None = None,
    ) -> int:
        """Detect cannibalization pairs within a single cluster.

        Uses:
        1. pgvector cosine distance between all post pairs (via embedding)
        2. GSC query overlap between post pairs

        thresholds: site-specific calibrated thresholds (flag/high/critical)

        Returns the number of pairs found.
        """
        t_flag = thresholds["flag"] if thresholds else COSINE_THRESHOLD_FLAG
        t_high = thresholds["high"] if thresholds else COSINE_THRESHOLD_HIGH
        t_critical = thresholds["critical"] if thresholds else COSINE_THRESHOLD_CRITICAL
        # Get posts with their embeddings (using pgvector for cosine distance)
        posts = await db.fetch(
            """
            SELECT p.id, p.title, p.url, p.word_count,
                   p.content_hash, p.content_intent, p.language, p.headings,
                   pe.embedding::text AS embedding_text
            FROM post_clusters pc
            JOIN posts p ON p.id = pc.post_id
            LEFT JOIN post_embeddings pe ON pe.post_id = p.id
            WHERE pc.cluster_id = $1
            ORDER BY p.id
            """,
            cluster_id,
        )

        if len(posts) < 2:
            return 0

        # Build maps for language, intent, and headings
        lang_map: dict = {p["id"]: p["language"] for p in posts}
        intent_map: dict = {p["id"]: p["content_intent"] for p in posts}
        headings_map: dict = {p["id"]: (p["headings"] or []) for p in posts}

        # Get health scores for "stronger post" determination
        health_rows = await db.fetch(
            """
            SELECT post_id, composite_score, traffic_contribution
            FROM post_health_scores
            WHERE post_id = ANY($1::uuid[])
            """,
            [p["id"] for p in posts],
        )
        health_map: dict[UUID, dict] = {
            r["post_id"]: {
                "score": r["composite_score"] or 0.0,
                "traffic": r["traffic_contribution"] or 0.0,
            }
            for r in health_rows
        }

        # Get GSC queries per post (recent 90 days)
        query_rows = await db.fetch(
            """
            SELECT post_id, query
            FROM gsc_metrics
            WHERE post_id = ANY($1::uuid[])
              AND date >= CURRENT_DATE - INTERVAL '90 days'
            GROUP BY post_id, query
            """,
            [p["id"] for p in posts],
        )
        queries_by_post: dict[UUID, set[str]] = {}
        for r in query_rows:
            queries_by_post.setdefault(r["post_id"], set()).add(r["query"].lower())

        pairs_found = 0
        post_list = list(posts)
        post_id_set = {p["id"] for p in post_list}

        # ── HNSW pre-filter: only compare posts above similarity threshold ──
        # Instead of O(n²) pair scan, use pgvector's HNSW index to find
        # nearest neighbors for each post. Much faster for large clusters.
        # For small clusters (< 20 posts), full scan is fine.
        use_hnsw = len(post_list) >= 20

        # Build pre-filtered candidate pairs via HNSW
        hnsw_candidates: dict[tuple[UUID, UUID], float] = {}
        if use_hnsw:
            for post in post_list:
                if not post["embedding_text"]:
                    continue
                # Use HNSW index to find nearest neighbors within threshold
                neighbors = await db.fetch(
                    """
                    SELECT pe2.post_id,
                           1 - (pe1.embedding <=> pe2.embedding) AS similarity
                    FROM post_embeddings pe1, post_embeddings pe2
                    WHERE pe1.post_id = $1
                      AND pe2.post_id != $1
                      AND pe2.post_id = ANY($2::uuid[])
                    ORDER BY pe1.embedding <=> pe2.embedding
                    LIMIT 10
                    """,
                    post["id"], list(post_id_set),
                )
                for n in neighbors:
                    sim = float(n["similarity"])
                    if sim >= t_flag:
                        pair_key = tuple(sorted([post["id"], n["post_id"]]))
                        hnsw_candidates[pair_key] = max(
                            hnsw_candidates.get(pair_key, 0), sim,
                        )
            logger.info(
                "HNSW pre-filter: %d candidate pairs from %d posts in cluster %s",
                len(hnsw_candidates), len(post_list), cluster_id,
            )

        # Build post lookup for iteration
        post_by_id = {p["id"]: p for p in post_list}

        # Determine which pairs to evaluate
        if use_hnsw:
            # Only evaluate HNSW candidates + all query-overlap pairs
            pair_iter = set(hnsw_candidates.keys())
            # Also add all pairs where posts share GSC queries
            for i, j in combinations(range(len(post_list)), 2):
                pa, pb = post_list[i], post_list[j]
                qa = queries_by_post.get(pa["id"], set())
                qb = queries_by_post.get(pb["id"], set())
                if qa & qb:
                    pair_iter.add(tuple(sorted([pa["id"], pb["id"]])))
        else:
            # Small cluster: full scan
            pair_iter = set()
            for i, j in combinations(range(len(post_list)), 2):
                pair_iter.add(tuple(sorted([post_list[i]["id"], post_list[j]["id"]])))

        for pair_key in pair_iter:
            pid_a, pid_b = pair_key
            post_a = post_by_id[pid_a]
            post_b = post_by_id[pid_b]

            # ── Skip duplicate content (same hash = redirect issue, not cannibalization) ──
            hash_a = post_a.get("content_hash")
            hash_b = post_b.get("content_hash")
            if hash_a and hash_b and hash_a == hash_b:
                continue

            # ── Skip cross-language pairs (e.g. EN vs UK tool pages) ──
            lang_a = lang_map.get(pid_a)
            lang_b = lang_map.get(pid_b)
            if lang_a and lang_b and lang_a != lang_b:
                continue

            # ── Signal 1: Embedding cosine similarity ──
            cosine_sim = hnsw_candidates.get(pair_key) if use_hnsw else None
            if cosine_sim is None and post_a["embedding_text"] and post_b["embedding_text"]:
                row = await db.fetchrow(
                    """
                    SELECT 1 - (a.embedding <=> b.embedding) AS similarity
                    FROM post_embeddings a, post_embeddings b
                    WHERE a.post_id = $1 AND b.post_id = $2
                    """,
                    post_a["id"], post_b["id"],
                )
                if row:
                    cosine_sim = float(row["similarity"])

            # ── Signal 2: GSC query overlap ──
            queries_a = queries_by_post.get(post_a["id"], set())
            queries_b = queries_by_post.get(post_b["id"], set())
            shared_queries = queries_a & queries_b
            n_shared = len(shared_queries)

            # ── Determine if this is a cannibalization pair ──
            # Intent-aware: raise threshold when intents differ (different search purposes)
            intent_a = intent_map.get(post_a["id"])
            intent_b = intent_map.get(post_b["id"])
            effective_flag = t_flag
            if intent_a and intent_b and intent_a != intent_b:
                effective_flag = t_flag + 0.10

            is_cannibal = False
            if cosine_sim is not None and cosine_sim >= effective_flag:
                is_cannibal = True
            if n_shared >= MIN_SHARED_QUERIES:
                is_cannibal = True

            if not is_cannibal:
                continue

            # ── Compute blended cannibalization score ──
            # Replaces raw cosine as the primary scoring signal.
            # Answers: "Would a human typing a single search query be
            # satisfied by either post?"
            h_a = headings_map.get(post_a["id"], [])
            h_b = headings_map.get(post_b["id"], [])

            if n_shared > 0:
                # With GSC data, we have ground truth — query overlap proves cannibalization
                # Boost the blended score proportionally to shared queries
                blended, severity = self._compute_severity(
                    cosine_sim, n_shared,
                    t_flag=t_flag, t_high=t_high, t_critical=t_critical,
                ), None
                blended_score, blended_tier = compute_blended_cannibalization_score(
                    post_a, post_b, h_a, h_b, cosine_sim,
                )
                # GSC query overlap overrides the blended tier — shared queries = real cannibalization
                severity = self._compute_severity(
                    cosine_sim, n_shared,
                    t_flag=t_flag, t_high=t_high, t_critical=t_critical,
                )
                overlap_score = max(blended_score, 0.5)  # Floor at 0.5 when GSC confirms
            else:
                # No GSC data — use the blended score as the sole arbiter
                blended_score, blended_tier = compute_blended_cannibalization_score(
                    post_a, post_b, h_a, h_b, cosine_sim,
                )
                # Filter out "content series" (blended score too low)
                if blended_tier == "low":
                    continue
                severity = blended_tier
                overlap_score = blended_score

            # ── Determine stronger post ──
            health_a = health_map.get(post_a["id"], {"score": 0, "traffic": 0})
            health_b = health_map.get(post_b["id"], {"score": 0, "traffic": 0})

            strength_a = health_a["score"] + health_a["traffic"] * 10
            strength_b = health_b["score"] + health_b["traffic"] * 10
            stronger_id = post_a["id"] if strength_a >= strength_b else post_b["id"]

            # Numeric severity score (0-100)
            severity_score = min(100.0, blended_score * 100)

            # Resolution recommendation based on blended tier
            resolution = self._recommend_resolution(
                cosine_sim, severity,
                post_a.get("content_intent"), post_b.get("content_intent"),
            )

            # ── Insert pair ──
            await db.execute(
                """
                INSERT INTO cannibalization_pairs
                    (cluster_id, post_a_id, post_b_id, overlap_score, severity,
                     overlapping_queries, cosine_similarity, stronger_post_id,
                     severity_score, resolution)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                cluster_id,
                post_a["id"],
                post_b["id"],
                overlap_score,
                severity,
                list(shared_queries)[:50] if shared_queries else None,
                cosine_sim,
                stronger_id,
                severity_score,
                resolution,
            )

            pairs_found += 1

        return pairs_found

    @staticmethod
    def _recommend_resolution(
        cosine_sim: float,
        severity: str,
        intent_a: str | None = None,
        intent_b: str | None = None,
    ) -> str:
        """Recommend a resolution action for a cannibalization pair."""
        if cosine_sim >= 0.95:
            return "redirect"  # Near-identical → 301 redirect shorter to longer
        if intent_a and intent_b and intent_a != intent_b:
            return "differentiate"  # Different intents → refocus each on its intent
        if severity == "critical" or cosine_sim >= 0.85:
            return "merge"  # High overlap, same intent → merge into stronger
        return "monitor"  # Moderate overlap → add internal link, monitor

    @staticmethod
    def _compute_severity(
        cosine_sim: float | None,
        n_shared: int,
        t_flag: float = COSINE_THRESHOLD_FLAG,
        t_high: float = COSINE_THRESHOLD_HIGH,
        t_critical: float = COSINE_THRESHOLD_CRITICAL,
    ) -> str:
        """Determine cannibalization severity from both signals.

        Accepts site-specific thresholds for calibrated detection.
        Falls back to module-level defaults if not provided.
        """
        has_cosine = cosine_sim is not None

        # Critical: very high cosine + shared queries
        if has_cosine and cosine_sim >= t_critical and n_shared > 0:
            return "critical"

        # High: high cosine, or moderate cosine + shared queries
        if has_cosine and cosine_sim >= t_high:
            return "high"
        if has_cosine and cosine_sim >= t_flag and n_shared > 0:
            return "high"

        # Medium: cosine above threshold, or many shared queries
        if has_cosine and cosine_sim >= t_flag:
            return "medium"
        if n_shared >= 3:
            return "medium"

        # Low: few shared queries only
        return "low"

    @staticmethod
    def _compute_overlap_score(
        cosine_sim: float | None,
        n_shared: int,
        queries_a: set[str],
        queries_b: set[str],
    ) -> float:
        """Compute combined overlap score (0.0-1.0) from both signals.

        Weighted average of cosine similarity and Jaccard similarity on queries.
        """
        scores = []

        if cosine_sim is not None:
            scores.append(cosine_sim)

        if queries_a or queries_b:
            union_size = len(queries_a | queries_b)
            if union_size > 0:
                jaccard = n_shared / union_size
                scores.append(jaccard)

        if not scores:
            return 0.0

        # If both signals present, weight cosine higher (70/30)
        if len(scores) == 2:
            return 0.7 * scores[0] + 0.3 * scores[1]

        return scores[0]
