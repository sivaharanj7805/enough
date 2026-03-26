"""Phase 2 Comprehensive Tests — edge cases, boundary conditions, error paths.

Tests everything that could go wrong in production. No mercy.
"""

import json
import math
import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.services.health_scoring import (
    _compute_trend, _ranking_score, _engagement_score,
    _freshness_score, _content_depth_score, _technical_seo_score,
    _assign_role, _assign_ecosystem_state,
)
from app.services.cannibalization import CannibalizationDetector
from app.services.clustering import TopicClusterer, _parse_pgvector
from app.services.recommendations import RecommendationEngine
from app.utils.url_normalize import normalize_url, urls_are_same
from app.utils.token_guard import truncate_for_api, truncate_body_texts


def _has_umap():
    try:
        import umap  # noqa: F401
        import hdbscan  # noqa: F401
        return True
    except ImportError:
        return False


# ═══════════════════════════════════════════════
# Health Scoring — Every Factor Thoroughly
# ═══════════════════════════════════════════════

class TestTrafficTrendEdgeCases:

    def test_dead_at_exactly_4_clicks(self):
        trend, score = _compute_trend(2, 2, 4)
        assert trend == "dead"

    def test_not_dead_at_5_clicks(self):
        trend, _ = _compute_trend(3, 2, 5)
        assert trend != "dead"

    def test_growing_at_exactly_16_percent(self):
        trend, _ = _compute_trend(116, 100, 216)
        assert trend == "growing"

    def test_stable_at_exactly_15_percent_increase(self):
        trend, _ = _compute_trend(115, 100, 215)
        assert trend == "stable"

    def test_declining_at_exactly_16_percent_drop(self):
        trend, _ = _compute_trend(84, 100, 184)
        assert trend == "declining"

    def test_stable_at_exactly_15_percent_decrease(self):
        trend, _ = _compute_trend(85, 100, 185)
        assert trend == "stable"

    def test_previous_zero_current_positive(self):
        trend, score = _compute_trend(100, 0, 100)
        assert trend == "growing"
        assert score == 100.0

    def test_previous_zero_current_zero_but_enough_total(self):
        """Both periods zero but total >= 5 → stable (traffic was in overlap window)."""
        trend, _ = _compute_trend(0, 0, 10)
        assert trend == "stable"

    def test_massive_growth(self):
        trend, score = _compute_trend(10000, 100, 10100)
        assert trend == "growing"
        assert score <= 100.0

    def test_massive_decline(self):
        trend, score = _compute_trend(1, 10000, 10001)
        assert trend == "declining"
        assert score >= 0.0

    def test_score_never_exceeds_100(self):
        _, score = _compute_trend(999999, 1, 1000000)
        assert score <= 100.0

    def test_score_never_below_0(self):
        _, score = _compute_trend(0, 999999, 999999)
        assert score >= 0.0


class TestRankingScoreEdgeCases:

    def test_position_below_1(self):
        score = _ranking_score(0.5)
        assert 0 <= score <= 100

    def test_position_exactly_1(self):
        assert _ranking_score(1.0) == 100.0

    def test_position_exactly_50(self):
        assert _ranking_score(50.0) == 0.0

    def test_position_100(self):
        assert _ranking_score(100.0) == 0.0

    def test_monotonically_decreasing(self):
        prev_score = 100.0
        for pos in range(2, 50):
            score = _ranking_score(float(pos))
            assert score <= prev_score, f"Score increased at position {pos}"
            prev_score = score

    def test_fractional_position(self):
        score = _ranking_score(3.7)
        assert 0 <= score <= 100


class TestEngagementScoreEdgeCases:

    def test_zero_bounce_max_time(self):
        score = _engagement_score(0.0, 300.0)
        assert score >= 95

    def test_full_bounce_zero_time(self):
        score = _engagement_score(1.0, 0.0)
        assert score == 0.0

    def test_impossible_bounce_over_1(self):
        score = _engagement_score(1.5, 60.0)
        assert isinstance(score, float)

    def test_negative_time(self):
        score = _engagement_score(0.5, -10.0)
        assert isinstance(score, float)

    def test_very_long_session(self):
        score = _engagement_score(0.0, 1000.0)
        assert score <= 100.0

    def test_exact_thresholds(self):
        score = _engagement_score(0.5, 150.0)
        assert 30 < score < 70


class TestFreshnessScoreEdgeCases:

    def test_future_date(self):
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=30)
        score = _freshness_score(future, now)
        assert score == 100.0

    def test_naive_datetime(self):
        now = datetime.now(timezone.utc)
        naive = datetime(2025, 1, 1, 0, 0, 0)
        score = _freshness_score(naive, now)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_exact_boundary_1_month(self):
        now = datetime.now(timezone.utc)
        exactly_1m = now - timedelta(days=31)
        score = _freshness_score(exactly_1m, now)
        # ~1.02 months old → continuous decay ≈ 95.0
        assert abs(score - 95.0) < 2.0

    def test_exact_boundary_3_months(self):
        now = datetime.now(timezone.utc)
        exactly_3m = now - timedelta(days=92)
        score = _freshness_score(exactly_3m, now)
        # ~3.02 months old → continuous decay ≈ 86.0
        assert abs(score - 86.0) < 2.0

    def test_very_old_post(self):
        now = datetime.now(timezone.utc)
        ancient = now - timedelta(days=3650)
        score = _freshness_score(ancient, now)
        assert score == 45.0  # Evergreen floor for non-time-sensitive content


class TestContentDepthEdgeCases:

    def test_zero_word_count(self):
        # 0 words: absolute=0, relative=15 (ratio 0), base=7.5
        score = _content_depth_score(0, 1000)
        assert abs(score - 7.5) < 2.0

    def test_zero_cluster_avg(self):
        score = _content_depth_score(500, 0)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_negative_cluster_avg(self):
        score = _content_depth_score(500, -100)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_exactly_500_words(self):
        # 500 words: absolute=20, relative=35 (ratio 0.5), base=27.5
        score = _content_depth_score(500, 1000)
        assert score > 25

    def test_word_count_equals_cluster_avg(self):
        # 1000 words: absolute=40, relative=60, base=50
        score = _content_depth_score(1000, 1000)
        assert 45 <= score <= 55

    def test_double_cluster_avg(self):
        # 2000 words: absolute=80, relative=100, base=90
        score = _content_depth_score(2000, 1000)
        assert score >= 85

    def test_never_exceeds_100(self):
        score = _content_depth_score(100000, 100)
        assert score <= 100.0


class TestTechnicalSEOEdgeCases:

    def test_empty_meta_description(self):
        score = _technical_seo_score("", "Good Title For SEO Ranking", None, False, False)
        assert score < 40

    def test_very_short_meta(self):
        score = _technical_seo_score("Short", "Good Title For SEO Ranking", None, False, False)
        assert score < 40

    def test_title_exactly_30_chars(self):
        score = _technical_seo_score(None, "A" * 30, None, False, False)
        assert score == 12.5  # 1 of 8 checks: title in 30-60 range

    def test_title_exactly_60_chars(self):
        score = _technical_seo_score(None, "A" * 60, None, False, False)
        assert score == 12.5  # 1 of 8 checks: title in 30-60 range

    def test_title_29_chars(self):
        score_29 = _technical_seo_score(None, "A" * 29, None, False, False)
        score_30 = _technical_seo_score(None, "A" * 30, None, False, False)
        assert score_30 >= score_29

    def test_headings_as_json_string(self):
        headings_json = json.dumps([{"level": "h2", "text": "Test"}])
        score = _technical_seo_score(None, "Title", headings_json, False, False)
        assert score == 12.5  # Only headings check passes ("Title" is 5 chars, too short)

    def test_headings_invalid_json(self):
        score = _technical_seo_score(None, "Title", "not json", False, False)
        assert isinstance(score, float)

    def test_headings_only_h1(self):
        headings = [{"level": "h1", "text": "Title"}]
        score = _technical_seo_score(None, "Title", headings, False, False)
        assert score < 40

    def test_none_title(self):
        score = _technical_seo_score(None, None, None, False, False)
        assert score == 0.0

    def test_all_pass(self):
        """5 of 8 checks pass without body_html (no OG, JSON-LD, canonical)."""
        title = "A Perfect Blog Post Title For SEO"  # 33 chars (30-60 range)
        assert 30 <= len(title) <= 60
        score = _technical_seo_score(
            "A detailed meta description for SEO purposes.",
            title,
            [{"level": "h2", "text": "Section 1"}, {"level": "h3", "text": "Sub"}],
            True, True,
        )
        # 5 checks × 12.5 = 62.5 (no body_html → OG/JSON-LD/canonical fail)
        assert score == 62.5


class TestRoleAssignment:

    def test_dead_weight_boundary(self):
        assert _assign_role(14.9, 0.1, 10, False) == "dead_weight"

    def test_supporter_at_boundary(self):
        assert _assign_role(30, 0.1, 10, False) == "supporter"
        assert _assign_role(29, 0.1, 10, False) == "dead_weight"

    def test_pillar_needs_both_conditions(self):
        assert _assign_role(40, 0.26, 100, False) == "pillar"
        assert _assign_role(40, 0.24, 100, False) == "supporter"
        assert _assign_role(39, 0.30, 100, False) == "supporter"

    def test_competitor_always_wins(self):
        assert _assign_role(100, 0.5, 10000, True) == "competitor"


class TestEcosystemState:

    def _m(self, role="supporter", trend="stable", traffic=100, days_ago=90):
        now = datetime.now(timezone.utc)
        return {
            "role": role, "trend": trend, "traffic": traffic,
            "publish_date": now - timedelta(days=days_ago),
            "composite": 50.0,
        }

    def test_seedbed_requires_small_cluster(self):
        now = datetime.now(timezone.utc)
        metrics = [self._m(days_ago=5), self._m(days_ago=10), self._m(days_ago=15)]
        state = _assign_ecosystem_state(metrics, 0, 3, 50.0, now, now - timedelta(days=30))
        assert state == "seedbed"

    def test_seedbed_not_with_4_posts(self):
        now = datetime.now(timezone.utc)
        metrics = [self._m(days_ago=5) for _ in range(4)]
        state = _assign_ecosystem_state(metrics, 0, 4, 50.0, now, now - timedelta(days=30))
        assert state != "seedbed"

    def test_swamp_cannibalization_threshold(self):
        now = datetime.now(timezone.utc)
        metrics = [self._m(days_ago=120) for _ in range(4)]
        state = _assign_ecosystem_state(metrics, 4, 4, 50.0, now, now - timedelta(days=30))
        assert state == "swamp"

    def test_swamp_no_pillar_large_cluster(self):
        now = datetime.now(timezone.utc)
        metrics = [self._m(days_ago=120) for _ in range(9)]
        state = _assign_ecosystem_state(metrics, 0, 9, 50.0, now, now - timedelta(days=30))
        assert state == "swamp"

    def test_desert_all_dead(self):
        now = datetime.now(timezone.utc)
        metrics = [self._m(trend="dead", traffic=0, days_ago=500) for _ in range(5)]
        state = _assign_ecosystem_state(metrics, 0, 5, 5.0, now, now - timedelta(days=30))
        assert state == "desert"

    def test_forest_requires_pillar_plus_health(self):
        now = datetime.now(timezone.utc)
        metrics = [
            self._m(role="pillar", trend="growing", traffic=5000, days_ago=120),
            self._m(role="supporter", trend="stable", traffic=1000, days_ago=120),
        ]
        state = _assign_ecosystem_state(metrics, 0, 2, 60.0, now, now - timedelta(days=30))
        assert state == "forest"

    def test_forest_blocked_by_high_cannibalization(self):
        now = datetime.now(timezone.utc)
        metrics = [
            self._m(role="pillar", trend="growing", traffic=5000, days_ago=120),
            self._m(role="supporter", trend="stable", traffic=1000, days_ago=120),
            self._m(role="supporter", trend="stable", traffic=800, days_ago=120),
        ]
        state = _assign_ecosystem_state(metrics, 2, 3, 60.0, now, now - timedelta(days=30))
        assert state == "swamp"


# ═══════════════════════════════════════════════
# Cannibalization — Dual Signal Thorough
# ═══════════════════════════════════════════════

class TestCannibalizationSeverityExhaustive:

    def test_no_cosine_no_queries(self):
        sev = CannibalizationDetector._compute_severity(None, 0)
        assert sev == "low"

    def test_cosine_just_below_threshold(self):
        sev = CannibalizationDetector._compute_severity(0.39, 0)
        assert sev == "low"

    def test_cosine_exactly_at_threshold(self):
        sev = CannibalizationDetector._compute_severity(0.45, 0)
        assert sev == "medium"

    def test_cosine_between_high_and_critical(self):
        sev = CannibalizationDetector._compute_severity(0.60, 0)
        assert sev == "high"

    def test_cosine_exactly_0_65_no_queries(self):
        sev = CannibalizationDetector._compute_severity(0.65, 0)
        assert sev == "high"  # Critical requires shared queries

    def test_cosine_0_65_with_queries(self):
        sev = CannibalizationDetector._compute_severity(0.65, 1)
        assert sev == "critical"

    def test_only_1_shared_query(self):
        sev = CannibalizationDetector._compute_severity(None, 1)
        assert sev == "low"

    def test_exactly_3_shared_queries(self):
        sev = CannibalizationDetector._compute_severity(None, 3)
        assert sev == "medium"


class TestOverlapScoreEdgeCases:

    def test_empty_query_sets(self):
        score = CannibalizationDetector._compute_overlap_score(0.50, 0, set(), set())
        assert score == 0.50

    def test_identical_query_sets(self):
        qa = {"seo", "content", "blog"}
        score = CannibalizationDetector._compute_overlap_score(None, 3, qa, qa)
        assert score == 1.0

    def test_no_overlap_queries(self):
        qa = {"seo", "content"}
        qb = {"marketing", "sales"}
        score = CannibalizationDetector._compute_overlap_score(None, 0, qa, qb)
        assert score == 0.0

    def test_weighted_combination(self):
        qa = {"a", "b", "c", "d"}
        qb = {"a", "b", "e", "f"}
        score = CannibalizationDetector._compute_overlap_score(0.50, 2, qa, qb)
        expected = 0.7 * 0.50 + 0.3 * (2/6)
        assert abs(score - expected) < 0.01


# ═══════════════════════════════════════════════
# Clustering — Edge Cases
# ═══════════════════════════════════════════════

class TestClusteringEdgeCases:

    def test_parse_pgvector_whitespace(self):
        result = _parse_pgvector("  [ 1.0 , 2.0 , 3.0 ]  ")
        assert result == [1.0, 2.0, 3.0]

    def test_parse_pgvector_negative_values(self):
        result = _parse_pgvector("[-0.5,0.3,-0.1]")
        assert result == [-0.5, 0.3, -0.1]

    def test_parse_pgvector_scientific_notation(self):
        result = _parse_pgvector("[1.5e-3,2.0e2]")
        assert abs(result[0] - 0.0015) < 1e-6
        assert result[1] == 200.0

    def test_simple_2d_layout_positions_unique(self):
        clusterer = TopicClusterer.__new__(TopicClusterer)
        positions = clusterer._simple_2d_layout(6)
        pos_set = set()
        for i in range(6):
            pos_tuple = (round(positions[i, 0], 4), round(positions[i, 1], 4))
            assert pos_tuple not in pos_set
            pos_set.add(pos_tuple)

    @pytest.mark.skipif(not _has_umap(), reason="umap-learn not installed")
    def test_adaptive_min_cluster_size_small(self):
        clusterer = TopicClusterer.__new__(TopicClusterer)
        rng = np.random.RandomState(42)
        embeddings = rng.randn(10, 50).astype(np.float32)
        labels, pos = clusterer._run_clustering_and_2d(embeddings, 10)
        assert len(labels) == 10

    @pytest.mark.skipif(not _has_umap(), reason="umap-learn not installed")
    def test_adaptive_min_cluster_size_medium(self):
        clusterer = TopicClusterer.__new__(TopicClusterer)
        rng = np.random.RandomState(42)
        embeddings = rng.randn(30, 50).astype(np.float32)
        labels, pos = clusterer._run_clustering_and_2d(embeddings, 30)
        assert len(labels) == 30


# ═══════════════════════════════════════════════
# Recommendation Engine — Error Handling
# ═══════════════════════════════════════════════

class TestRecommendationJsonParsing:

    def _engine(self):
        return RecommendationEngine.__new__(RecommendationEngine)

    def test_nested_json(self):
        result = self._engine()._parse_json('{"a": {"b": [1, 2, 3]}}')
        assert result["a"]["b"] == [1, 2, 3]

    def test_json_with_newlines(self):
        result = self._engine()._parse_json('{\n  "key": "value"\n}')
        assert result["key"] == "value"

    def test_json_with_unicode(self):
        result = self._engine()._parse_json('{"title": "How to use émojis 🎉"}')
        assert "émojis" in result["title"]

    def test_multiple_json_objects(self):
        result = self._engine()._parse_json('{"a": 1}\n{"b": 2}')
        # Should parse the first valid JSON object
        assert isinstance(result, dict)

    def test_empty_string(self):
        result = self._engine()._parse_json("")
        assert "raw_response" in result

    def test_just_whitespace(self):
        result = self._engine()._parse_json("   \n\n  ")
        assert "raw_response" in result

    def test_markdown_json_block(self):
        result = self._engine()._parse_json("```json\n{\"key\": \"val\"}\n```")
        assert result["key"] == "val"

    def test_markdown_block_no_lang(self):
        result = self._engine()._parse_json("```\n{\"key\": \"val\"}\n```")
        assert result["key"] == "val"

    def test_preamble_and_postamble(self):
        result = self._engine()._parse_json(
            "Sure! Here's the analysis:\n\n{\"key\": \"val\"}\n\nLet me know."
        )
        assert result["key"] == "val"


class TestRecommendationHeadingFormat:

    def _engine(self):
        return RecommendationEngine.__new__(RecommendationEngine)

    def test_max_headings_capped(self):
        headings = [{"level": f"h{(i%3)+2}", "text": f"Heading {i}"} for i in range(20)]
        result = self._engine()._format_headings(headings)
        assert result.count(":") <= 15

    def test_mixed_valid_invalid_headings(self):
        headings = [
            {"level": "h2", "text": "Valid"},
            {"invalid": "data"},
            {"level": "h3", "text": "Also Valid"},
            "not a dict",
        ]
        result = self._engine()._format_headings(headings)
        assert "Valid" in result

    def test_integer_headings(self):
        e = self._engine()
        assert e._format_headings(42) == "None"
        assert e._format_headings(0) == "None"


# ═══════════════════════════════════════════════
# URL Normalization Edge Cases
# ═══════════════════════════════════════════════

class TestURLNormalizationExhaustive:

    def test_multiple_trailing_slashes(self):
        assert normalize_url("https://example.com/post///") == "https://example.com/post"

    def test_query_param_ordering(self):
        a = normalize_url("https://example.com/post?z=1&a=2")
        b = normalize_url("https://example.com/post?a=2&z=1")
        assert a == b

    def test_mixed_case_utm_params(self):
        result = normalize_url("https://example.com/post?UTM_SOURCE=twitter")
        assert "utm_source" not in result.lower() or "UTM_SOURCE" not in result

    def test_preserves_meaningful_query_params(self):
        result = normalize_url("https://example.com/search?q=hello+world&page=3")
        assert "q=" in result
        assert "page=3" in result

    def test_port_8080_preserved(self):
        result = normalize_url("https://example.com:8080/post")
        assert "8080" in result

    def test_anchor_with_slash(self):
        result = normalize_url("https://example.com/post/#section/1")
        assert "#" not in result

    def test_urls_are_same_comprehensive(self):
        assert urls_are_same(
            "http://WWW.Example.COM:80/Post/?utm_source=x#top",
            "https://example.com/Post",
        )

    def test_different_paths_not_same(self):
        assert not urls_are_same(
            "https://example.com/post-a",
            "https://example.com/post-b",
        )


# ═══════════════════════════════════════════════
# Security Edge Cases
# ═══════════════════════════════════════════════

class TestSecurityEdgeCases:

    @pytest.mark.asyncio
    async def test_cron_timing_attack_resistance(self):
        import inspect
        from app.dependencies import verify_cron_secret
        source = inspect.getsource(verify_cron_secret)
        assert "compare_digest" in source

    def test_oauth_state_empty_site_id(self):
        import hashlib, hmac, base64
        secret = "test-key"
        state_data = {"site_id": ""}
        state_json = json.dumps(state_data, separators=(",", ":"))
        state_b64 = base64.urlsafe_b64encode(state_json.encode()).decode()
        state_sig = hmac.new(secret.encode(), state_b64.encode(), hashlib.sha256).hexdigest()[:16]
        assert len(state_sig) == 16

    def test_encryption_roundtrip_special_chars(self):
        from app.utils.encryption import encrypt_value, decrypt_value
        special = "p@$$w0rd!#%^&*()_+-={}[]|\\:\";<>?,./"
        assert decrypt_value(encrypt_value(special)) == special

    def test_encryption_unicode(self):
        from app.utils.encryption import encrypt_value, decrypt_value
        unicode_str = "日本語テスト 🎉 émojis"
        assert decrypt_value(encrypt_value(unicode_str)) == unicode_str

    def test_encryption_long_string(self):
        from app.utils.encryption import encrypt_value, decrypt_value
        long_str = "x" * 10000
        assert decrypt_value(encrypt_value(long_str)) == long_str


# ═══════════════════════════════════════════════
# Token Guard Edge Cases
# ═══════════════════════════════════════════════

class TestTokenGuardEdgeCases:

    def test_empty_content(self):
        assert truncate_for_api("") == ""

    def test_none_content(self):
        assert truncate_for_api(None) is None

    def test_content_exactly_at_limit(self):
        content = "x" * 1000
        result = truncate_for_api(content, max_chars=1000)
        assert result == content

    def test_content_one_over_limit(self):
        content = "x" * 1001
        result = truncate_for_api(content, max_chars=1000)
        assert "[Content truncated" in result

    def test_truncate_body_texts_empty_list(self):
        assert truncate_body_texts([]) == []


# ═══════════════════════════════════════════════
# Schema Validation Exhaustive
# ═══════════════════════════════════════════════

class TestSchemaExhaustive:

    def test_all_recommendation_types_accepted(self):
        from app.models.schemas import RecommendationResponse
        for rtype in ["merge", "refresh", "optimize", "delete", "expand", "interlink", "growth"]:
            rec = RecommendationResponse(
                id=uuid4(), post_id=uuid4(),
                recommendation_type=rtype, priority="medium",
                title="Test", summary="Test",
                specific_actions=[], status="pending",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            assert rec.recommendation_type == rtype

    def test_all_status_values(self):
        from app.models.schemas import RecommendationStatusUpdate
        for status in ["pending", "in_progress", "completed", "dismissed"]:
            u = RecommendationStatusUpdate(status=status)
            assert u.status == status

    def test_problem_response_nullable_fields(self):
        from app.models.schemas import ContentProblemResponse
        p = ContentProblemResponse(
            id=uuid4(), post_id=uuid4(),
            problem_type="orphan", severity="high",
            details=None, detected_at=datetime.now(timezone.utc),
            resolved_at=None,
        )
        assert p.details is None
        assert p.resolved_at is None

    def test_recommendation_response_nullable_fields(self):
        from app.models.schemas import RecommendationResponse
        r = RecommendationResponse(
            id=uuid4(), post_id=uuid4(),
            problem_id=None,
            recommendation_type="growth", priority="medium",
            estimated_effort_hours=None, estimated_impact=None,
            title="Test", summary="Test",
            specific_actions=[], ai_generated_content=None,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert r.problem_id is None
        assert r.estimated_effort_hours is None
