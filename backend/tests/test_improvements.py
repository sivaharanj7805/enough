"""Tests for research-driven improvements:
1. Graceful degradation (dynamic weight rebalancing)
2. Auto-calibrate cosine thresholds
3. HNSW pre-filter awareness
4. Claude prompt improvements (confidence field)
5. Small cluster edge cases
6. Problem detection data awareness
"""

import pytest
from app.services.health_scoring import (
    compute_dynamic_weights,
    _content_depth_score,
    W_TRAFFIC_TREND,
    W_RANKING,
    W_ENGAGEMENT,
    W_FRESHNESS,
    W_CONTENT_DEPTH,
    W_INTERNAL_LINKS,
    W_TECHNICAL_SEO,
)
from app.services.cannibalization import (
    CannibalizationDetector,
    COSINE_THRESHOLD_FLAG,
    COSINE_THRESHOLD_HIGH,
    COSINE_THRESHOLD_CRITICAL,
)


# ═══════════════════════════════════════════════
# 1. Graceful Degradation — Dynamic Weights
# ═══════════════════════════════════════════════


class TestDynamicWeights:
    """Test weight rebalancing when data sources are missing."""

    def test_full_data_weights_unchanged(self):
        """All data available → original weights."""
        w = compute_dynamic_weights(has_ga4=True, has_gsc=True)
        assert abs(w["traffic_trend"] - W_TRAFFIC_TREND) < 1e-6
        assert abs(w["ranking"] - W_RANKING) < 1e-6
        assert abs(w["engagement"] - W_ENGAGEMENT) < 1e-6
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_no_ga4_zeroes_traffic_and_engagement(self):
        """No GA4 → traffic and engagement zeroed, others scaled up."""
        w = compute_dynamic_weights(has_ga4=False, has_gsc=True)
        assert w["traffic_trend"] == 0.0
        assert w["engagement"] == 0.0
        assert w["ranking"] > W_RANKING  # Scaled up
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_no_gsc_zeroes_ranking(self):
        """No GSC → ranking zeroed, others scaled up."""
        w = compute_dynamic_weights(has_ga4=True, has_gsc=False)
        assert w["ranking"] == 0.0
        assert w["traffic_trend"] > 0  # GA4 still provides traffic
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_no_external_data_crawl_only(self):
        """No GA4 or GSC → only crawl factors remain, scaled to 1.0."""
        w = compute_dynamic_weights(has_ga4=False, has_gsc=False)
        assert w["traffic_trend"] == 0.0
        assert w["ranking"] == 0.0
        assert w["engagement"] == 0.0
        # Remaining 40% of original → scaled to 100%
        assert w["freshness"] > 0
        assert w["content_depth"] > 0
        assert w["internal_links"] > 0
        assert w["technical_seo"] > 0
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_crawl_only_has_proxy_signals(self):
        """Crawl-only mode includes proxy engagement and structure signals."""
        w = compute_dynamic_weights(has_ga4=False, has_gsc=False)
        assert w.get("predicted_engagement", 0) > 0, "Missing predicted_engagement weight"
        assert w.get("content_structure", 0) > 0, "Missing content_structure weight"
        assert w["traffic_trend"] == 0.0
        assert w["ranking"] == 0.0
        assert w["engagement"] == 0.0

    def test_all_weights_sum_to_one(self):
        """Every combination should sum to 1.0."""
        for ga4 in [True, False]:
            for gsc in [True, False]:
                w = compute_dynamic_weights(has_ga4=ga4, has_gsc=gsc)
                assert abs(sum(w.values()) - 1.0) < 1e-6, (
                    f"ga4={ga4}, gsc={gsc}: sum={sum(w.values())}"
                )


# ═══════════════════════════════════════════════
# 2. Auto-Calibrate Thresholds
# ═══════════════════════════════════════════════


class TestThresholdCalibration:
    """Test cosine threshold auto-calibration logic."""

    def test_default_thresholds_are_sane(self):
        """Default thresholds are calibrated for text-embedding-3-small."""
        assert COSINE_THRESHOLD_FLAG == 0.45
        assert COSINE_THRESHOLD_HIGH == 0.55
        assert COSINE_THRESHOLD_CRITICAL == 0.65

    def test_severity_with_custom_thresholds(self):
        """Site-specific thresholds override defaults."""
        # Niche site with higher baseline → higher thresholds
        sev = CannibalizationDetector._compute_severity(
            0.55, 0, t_flag=0.50, t_high=0.60, t_critical=0.70,
        )
        assert sev == "medium"  # 0.55 >= flag(0.50) but < high(0.60)

        sev = CannibalizationDetector._compute_severity(
            0.65, 1, t_flag=0.50, t_high=0.60, t_critical=0.70,
        )
        assert sev == "high"  # 0.65 >= high(0.60) but < critical(0.70) w/shared

    def test_severity_critical_with_custom_thresholds(self):
        sev = CannibalizationDetector._compute_severity(
            0.75, 2, t_flag=0.50, t_high=0.60, t_critical=0.70,
        )
        assert sev == "critical"

    def test_severity_low_with_high_thresholds(self):
        """High thresholds should make moderate similarity → low severity."""
        sev = CannibalizationDetector._compute_severity(
            0.45, 0, t_flag=0.50, t_high=0.60, t_critical=0.70,
        )
        assert sev == "low"


# ═══════════════════════════════════════════════
# 3. Small Cluster Edge Cases
# ═══════════════════════════════════════════════


class TestSmallClusterEdgeCases:
    """Test edge cases for clusters with few posts."""

    def test_content_depth_with_industry_avg(self):
        """When cluster avg is used as industry avg (1000), scoring is sensible."""
        # 500 words: absolute=20, relative=35 (ratio 0.5), base=27.5
        score = _content_depth_score(500, 1000.0)
        assert abs(score - 27.5) < 2.0

        # 1000 words: absolute=40, relative=60 (ratio 1.0), base=50
        score = _content_depth_score(1000, 1000.0)
        assert 45.0 <= score <= 55.0

        # 2000 words: absolute=80, relative=100 (ratio 2.0), base=90
        score = _content_depth_score(2000, 1000.0)
        assert score >= 85.0

    def test_very_short_content(self):
        """< 300 words scores low regardless of avg (blended absolute + relative)."""
        # 200 words: absolute=8, relative=15 (ratio < 0.5), base=11.5
        score_500 = _content_depth_score(200, 500.0)
        score_1000 = _content_depth_score(200, 1000.0)
        score_10000 = _content_depth_score(200, 10000.0)
        assert score_500 < 15.0
        assert score_1000 < 15.0
        assert score_10000 < 15.0


# ═══════════════════════════════════════════════
# 4. Overlap Score Edge Cases
# ═══════════════════════════════════════════════


class TestOverlapScoreWithCalibration:
    """Test overlap score computation with different similarity ranges."""

    def test_low_similarity_v3_small_range(self):
        """Typical text-embedding-3-small range: 0.35-0.55."""
        score = CannibalizationDetector._compute_overlap_score(
            0.45, 0, set(), set(),
        )
        assert score == 0.45

    def test_combined_low_cosine_high_query_overlap(self):
        """Low cosine but high query overlap → combined score."""
        qa = {"keyword a", "keyword b", "keyword c"}
        qb = {"keyword a", "keyword b", "keyword d"}
        score = CannibalizationDetector._compute_overlap_score(
            0.35, 2, qa, qb,
        )
        # 0.7 * 0.35 + 0.3 * (2/4) = 0.245 + 0.15 = 0.395
        assert abs(score - 0.395) < 0.01


# ═══════════════════════════════════════════════
# 5. Recommendation Confidence
# ═══════════════════════════════════════════════


class TestRecommendationParsing:
    """Test that the recommendation engine handles confidence fields."""

    def test_parse_json_with_confidence(self):
        from app.services.recommendations import RecommendationEngine
        engine = RecommendationEngine.__new__(RecommendationEngine)

        result = engine._parse_json('{"action": "expand", "confidence": 0.85}')
        assert result["confidence"] == 0.85

    def test_parse_json_without_confidence(self):
        from app.services.recommendations import RecommendationEngine
        engine = RecommendationEngine.__new__(RecommendationEngine)

        result = engine._parse_json('{"action": "expand"}')
        assert "confidence" not in result

    def test_parse_json_with_code_block(self):
        from app.services.recommendations import RecommendationEngine
        engine = RecommendationEngine.__new__(RecommendationEngine)

        raw = '```json\n{"action": "expand", "confidence": 0.9}\n```'
        result = engine._parse_json(raw)
        assert result["action"] == "expand"
        assert result["confidence"] == 0.9

    def test_parse_json_fallback_to_raw(self):
        from app.services.recommendations import RecommendationEngine
        engine = RecommendationEngine.__new__(RecommendationEngine)

        result = engine._parse_json("This is not JSON at all")
        assert "raw_response" in result
