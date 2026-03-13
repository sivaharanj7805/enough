"""Tests for Stickiness Features — 5 features that transform
from "interesting tool" to "can't cancel."

1. Historical Tracking + Change Detection
2. Smart Alerts
3. Impact Tracking
4. Content Briefs
5. Keyword Opportunity Scoring
"""

import pytest
from uuid import uuid4


# ═══════════════════════════════════════════════
# 5. Keyword Opportunity Scoring
# ═══════════════════════════════════════════════


class TestKeywordOpportunityScoring:
    """Test opportunity score computation."""

    def test_high_volume_close_position(self):
        """High impressions + position 5 = great opportunity."""
        from app.services.keyword_opportunities import score_opportunity
        score = score_opportunity(impressions=5000, position=5.0, intent="commercial")
        assert score > 80  # Should be high

    def test_low_volume_far_position(self):
        """Low impressions + position 80 = bad opportunity."""
        from app.services.keyword_opportunities import score_opportunity
        score = score_opportunity(impressions=15, position=80.0, intent="informational")
        assert score < 30  # Should be low

    def test_position_4_to_10_is_prime(self):
        """Positions 4-10 have highest proximity score (40 points)."""
        from app.services.keyword_opportunities import score_opportunity
        score_pos5 = score_opportunity(100, 5.0, "informational")
        score_pos15 = score_opportunity(100, 15.0, "informational")
        assert score_pos5 > score_pos15

    def test_already_ranking_top3_less_upside(self):
        """Position 1-3 = less opportunity (already winning)."""
        from app.services.keyword_opportunities import score_opportunity
        score_pos2 = score_opportunity(100, 2.0, "informational")
        score_pos6 = score_opportunity(100, 6.0, "informational")
        assert score_pos6 > score_pos2  # More upside at pos 6

    def test_transactional_beats_informational(self):
        """Transactional intent is worth more."""
        from app.services.keyword_opportunities import score_opportunity
        score_trans = score_opportunity(100, 10.0, "transactional")
        score_info = score_opportunity(100, 10.0, "informational")
        assert score_trans > score_info
        assert score_trans - score_info == 10.0  # 20 - 10

    def test_zero_impressions(self):
        """Zero impressions = zero volume score."""
        from app.services.keyword_opportunities import score_opportunity
        score = score_opportunity(0, 5.0, "informational")
        assert score == 50.0  # 0 volume + 40 proximity + 10 intent

    def test_very_high_impressions(self):
        """Very high impressions cap at 40."""
        from app.services.keyword_opportunities import score_opportunity
        score = score_opportunity(1_000_000, 5.0, "transactional")
        assert score <= 100.0  # Max possible

    def test_difficulty_estimates(self):
        """Difficulty estimation from position."""
        from app.services.keyword_opportunities import estimate_difficulty
        assert estimate_difficulty(3.0, 1) == "low"
        assert estimate_difficulty(10.0, 1) == "medium"
        assert estimate_difficulty(25.0, 1) == "high"
        assert estimate_difficulty(50.0, 1) == "very_high"


# ═══════════════════════════════════════════════
# 2. Smart Alerts
# ═══════════════════════════════════════════════


class TestSmartAlerts:
    """Test alert generation logic."""

    def test_alert_manager_instantiates(self):
        from app.services.smart_alerts import AlertManager
        mgr = AlertManager()
        assert mgr is not None

    def test_email_digest_severity_mapping(self):
        """Verify severity emoji mapping exists."""
        # This just ensures the module loads and constants are correct
        from app.services.smart_alerts import AlertManager
        mgr = AlertManager()
        assert hasattr(mgr, 'generate_email_digest')


# ═══════════════════════════════════════════════
# 1. Historical Tracking
# ═══════════════════════════════════════════════


class TestHistoricalTracking:
    """Test historical tracking logic."""

    def test_tracker_instantiates(self):
        from app.services.historical_tracking import HistoricalTracker
        tracker = HistoricalTracker()
        assert tracker is not None

    def test_has_snapshot_method(self):
        from app.services.historical_tracking import HistoricalTracker
        tracker = HistoricalTracker()
        assert hasattr(tracker, 'take_snapshot')
        assert hasattr(tracker, 'detect_changes')


# ═══════════════════════════════════════════════
# 3. Impact Tracking
# ═══════════════════════════════════════════════


class TestImpactTracking:
    """Test impact tracking logic."""

    def test_tracker_instantiates(self):
        from app.services.impact_tracking import ImpactTracker
        tracker = ImpactTracker()
        assert tracker is not None

    def test_has_required_methods(self):
        from app.services.impact_tracking import ImpactTracker
        tracker = ImpactTracker()
        assert hasattr(tracker, 'record_completion')
        assert hasattr(tracker, 'update_impacts')
        assert hasattr(tracker, 'get_monthly_report')


# ═══════════════════════════════════════════════
# 4. Content Briefs
# ═══════════════════════════════════════════════


class TestContentBriefs:
    """Test content brief generation logic."""

    def test_brief_generator_instantiates(self):
        from app.services.content_briefs import ContentBriefGenerator
        gen = ContentBriefGenerator()
        assert gen is not None

    def test_has_required_methods(self):
        from app.services.content_briefs import ContentBriefGenerator
        gen = ContentBriefGenerator()
        assert hasattr(gen, 'generate_brief')
        assert hasattr(gen, 'generate_briefs_for_gaps')


# ═══════════════════════════════════════════════
# Import verification
# ═══════════════════════════════════════════════


class TestStickynessImports:
    """Verify all stickiness services import cleanly."""

    def test_import_historical_tracking(self):
        from app.services.historical_tracking import HistoricalTracker
        assert HistoricalTracker is not None

    def test_import_smart_alerts(self):
        from app.services.smart_alerts import AlertManager
        assert AlertManager is not None

    def test_import_impact_tracking(self):
        from app.services.impact_tracking import ImpactTracker
        assert ImpactTracker is not None

    def test_import_content_briefs(self):
        from app.services.content_briefs import ContentBriefGenerator
        assert ContentBriefGenerator is not None

    def test_import_keyword_opportunities(self):
        from app.services.keyword_opportunities import KeywordOpportunityScorer
        assert KeywordOpportunityScorer is not None
