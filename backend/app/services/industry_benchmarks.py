"""Industry benchmarks for contextualising health scores.

Percentile tables based on web research of blog post statistics by
vertical.  Used to transform raw scores into "how do you compare"
percentile rankings.
"""

from __future__ import annotations

BENCHMARKS: dict[str, dict[str, dict[str, float]]] = {
    "saas": {
        "word_count":   {"p10": 400, "p25": 800,  "p50": 1400, "p75": 2200, "p90": 3500},
        "flesch":       {"p10": 25,  "p25": 35,   "p50": 48,   "p75": 60,   "p90": 70},
        "health_score": {"p10": 15,  "p25": 30,   "p50": 50,   "p75": 68,   "p90": 82},
        "internal_links": {"p10": 0, "p25": 2,    "p50": 5,    "p75": 10,   "p90": 18},
    },
    "ecommerce": {
        "word_count":   {"p10": 300, "p25": 600,  "p50": 1000, "p75": 1600, "p90": 2500},
        "flesch":       {"p10": 30,  "p25": 40,   "p50": 55,   "p75": 65,   "p90": 75},
        "health_score": {"p10": 12,  "p25": 25,   "p50": 45,   "p75": 62,   "p90": 78},
        "internal_links": {"p10": 0, "p25": 3,    "p50": 7,    "p75": 15,   "p90": 25},
    },
    "media": {
        "word_count":   {"p10": 300, "p25": 500,  "p50": 900,  "p75": 1500, "p90": 2200},
        "flesch":       {"p10": 35,  "p25": 45,   "p50": 58,   "p75": 68,   "p90": 78},
        "health_score": {"p10": 10,  "p25": 22,   "p50": 42,   "p75": 60,   "p90": 75},
        "internal_links": {"p10": 1, "p25": 4,    "p50": 8,    "p75": 14,   "p90": 22},
    },
    "agency": {
        "word_count":   {"p10": 500, "p25": 900,  "p50": 1500, "p75": 2400, "p90": 3800},
        "flesch":       {"p10": 20,  "p25": 30,   "p50": 42,   "p75": 55,   "p90": 65},
        "health_score": {"p10": 12,  "p25": 28,   "p50": 48,   "p75": 65,   "p90": 80},
        "internal_links": {"p10": 0, "p25": 2,    "p50": 5,    "p75": 10,   "p90": 16},
    },
    "default": {
        "word_count":   {"p10": 350, "p25": 700,  "p50": 1200, "p75": 2000, "p90": 3000},
        "flesch":       {"p10": 28,  "p25": 38,   "p50": 50,   "p75": 62,   "p90": 72},
        "health_score": {"p10": 12,  "p25": 26,   "p50": 46,   "p75": 63,   "p90": 78},
        "internal_links": {"p10": 0, "p25": 2,    "p50": 5,    "p75": 10,   "p90": 18},
    },
}

# Keywords that hint at industry from cluster labels / content
INDUSTRY_HINTS: dict[str, list[str]] = {
    "saas": ["saas", "software", "crm", "erp", "api", "platform", "subscription", "onboarding",
             "churn", "mrr", "arr", "b2b", "pipeline", "demo"],
    "ecommerce": ["ecommerce", "e-commerce", "shopify", "woocommerce", "product", "cart",
                   "checkout", "shipping", "inventory", "marketplace"],
    "media": ["news", "journalism", "editorial", "magazine", "publisher", "content studio",
              "newsletter", "subscriber"],
    "agency": ["agency", "client", "freelance", "consulting", "marketing agency",
               "digital agency", "retainer"],
}


def detect_industry(cluster_labels: list[str], sample_titles: list[str]) -> str:
    """Auto-detect industry from cluster labels and post titles."""
    text = " ".join(cluster_labels + sample_titles).lower()
    scores: dict[str, int] = {}
    for industry, keywords in INDUSTRY_HINTS.items():
        scores[industry] = sum(1 for kw in keywords if kw in text)
    if not scores or max(scores.values()) == 0:
        return "default"
    return max(scores, key=scores.get)  # type: ignore[arg-type]


def compute_percentile(value: float, benchmarks: dict[str, float]) -> int:
    """Return approximate percentile (0-100) for a value given benchmark distribution."""
    pcts = [10, 25, 50, 75, 90]
    vals = [benchmarks[f"p{p}"] for p in pcts]

    if value <= vals[0]:
        return int(10 * value / max(vals[0], 1))
    if value >= vals[-1]:
        return min(99, 90 + int(10 * (value - vals[-1]) / max(vals[-1], 1)))

    for i in range(len(vals) - 1):
        if vals[i] <= value <= vals[i + 1]:
            lo_pct, hi_pct = pcts[i], pcts[i + 1]
            ratio = (value - vals[i]) / max(vals[i + 1] - vals[i], 1)
            return int(lo_pct + ratio * (hi_pct - lo_pct))

    return 50  # fallback


def benchmark_post(
    word_count: int,
    flesch_score: float,
    health_score: float,
    internal_links: int,
    industry: str = "default",
) -> dict[str, int]:
    """Return percentile rankings for a post across key metrics."""
    bench = BENCHMARKS.get(industry, BENCHMARKS["default"])
    return {
        "word_count_pct": compute_percentile(word_count, bench["word_count"]),
        "readability_pct": compute_percentile(flesch_score, bench["flesch"]),
        "health_pct": compute_percentile(health_score, bench["health_score"]),
        "internal_links_pct": compute_percentile(internal_links, bench["internal_links"]),
    }


def benchmark_site(
    avg_word_count: float,
    avg_flesch: float,
    avg_health: float,
    avg_internal_links: float,
    industry: str = "default",
) -> dict[str, int]:
    """Return percentile rankings for a site's averages."""
    bench = BENCHMARKS.get(industry, BENCHMARKS["default"])
    return {
        "word_count_pct": compute_percentile(avg_word_count, bench["word_count"]),
        "readability_pct": compute_percentile(avg_flesch, bench["flesch"]),
        "health_pct": compute_percentile(avg_health, bench["health_score"]),
        "internal_links_pct": compute_percentile(avg_internal_links, bench["internal_links"]),
    }
